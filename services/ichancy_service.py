"""
Ichancy API service with async operations, retry logic, and circuit breaker.
Handles all communication with the external Ichancy gaming platform.
"""
import asyncio
import time
from typing import Optional, Dict, Any
import requests
from requests.auth import HTTPBasicAuth
from dataclasses import dataclass

from config import config
from utils.logger import get_logger
from utils.retry import with_retry, get_circuit_breaker
from utils.exceptions import (
    IchancyException, IchancyPlayerException, IchancyBalanceException,
    APITimeoutException, APIConnectionException, APIResponseException,
    NetworkException
)

logger = get_logger("ichancy_service")

# Circuit breaker for Ichancy API
ichancy_circuit = get_circuit_breaker(
    "ichancy",
    failure_threshold=5,
    recovery_timeout=60.0
)


@dataclass
class IchancyResponse:
    """Standardized Ichancy API response."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    raw_response: Optional[Any] = None


class IchancyService:
    """
    Async Ichancy API client with resilience patterns.
    
    Features:
    - Async HTTP with httpx
    - Automatic retry with exponential backoff
    - Circuit breaker to prevent cascading failures
    - Comprehensive logging for audit trail
    """
    
    def __init__(
        self,
        api_url: str = None,
        username: str = None,
        password: str = None,
        timeout: float = None
    ):
        self.api_url = api_url or config.ICHANCY_API_URL
        self.auth = HTTPBasicAuth(
            username or config.ICHANCY_USERNAME,
            password or config.ICHANCY_PASSWORD
        )
        self.timeout = timeout or config.ICHANCY_TIMEOUT
    
    async def close(self):
        """No-op for requests-based implementation."""
        pass
    
    async def _request(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "POST"
    ) -> IchancyResponse:
        """
        Make API request with error handling using requests (sync but wrapped).
        
        Args:
            action: API action name
            params: Request parameters
            method: HTTP method (GET/POST)
            
        Returns:
            IchancyResponse with success status and data
        """
        start_time = time.time()
        request_data = {"action": action}
        if params:
            request_data.update(params)
        
        logger.debug(f"Ichancy API request: {action}", params=params)
        
        try:
            # Run the synchronous requests call in a thread to keep it async-friendly
            def _do_req():
                if method.upper() == "GET":
                    return requests.get(
                        self.api_url,
                        auth=self.auth,
                        params=request_data,
                        timeout=self.timeout
                    )
                else:
                    return requests.post(
                        self.api_url,
                        auth=self.auth,
                        data=request_data,
                        timeout=self.timeout
                    )
            
            response = await asyncio.to_thread(_do_req)
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Log API call for audit
            logger.audit_api_call(
                service="ichancy",
                action=action,
                success=response.status_code < 400,
                duration_ms=duration_ms,
                status_code=response.status_code
            )
            
            if response.status_code >= 400:
                logger.error(f"Ichancy API error: {response.status_code}", response=response.text)
                return IchancyResponse(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    raw_response=response.text
                )
            
            # Parse response
            try:
                data = response.json()
                
                # Check for API-level errors
                if isinstance(data, dict):
                    # The API returns 'hasError': 'yes' for errors
                    if data.get("hasError") == "yes" or data.get("error") or data.get("status") == "error":
                        error_msg = data.get("msg") or data.get("error") or data.get("message", "Unknown error")
                        return IchancyResponse(
                            success=False,
                            error=error_msg,
                            data=data,
                            raw_response=data
                        )
                
                return IchancyResponse(
                    success=True,
                    data=data,
                    raw_response=data
                )
                
            except ValueError:
                # Non-JSON response
                return IchancyResponse(
                    success=True,
                    data={"raw": response.text},
                    raw_response=response.text
                )
                
        except requests.Timeout as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.audit_api_call(
                service="ichancy",
                action=action,
                success=False,
                duration_ms=duration_ms,
                error="timeout"
            )
            raise APITimeoutException("ichancy", self.timeout) from e
            
        except requests.ConnectionError as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.audit_api_call(
                service="ichancy",
                action=action,
                success=False,
                duration_ms=duration_ms,
                error="connection_failed"
            )
            raise APIConnectionException("ichancy", str(e)) from e
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.audit_api_call(
                service="ichancy",
                action=action,
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )
            raise NetworkException(f"Ichancy API error: {e}") from e
    
    # ============ API Methods ============
    
    @with_retry(
        max_retries=3,
        exceptions=(NetworkException, APITimeoutException, APIConnectionException),
        circuit_breaker_name="ichancy"
    )
    async def check_status(self) -> IchancyResponse:
        """Check API availability."""
        return await self._request("checkStatus", method="GET")
    
    @with_retry(
        max_retries=2,
        exceptions=(NetworkException, APITimeoutException),
        circuit_breaker_name="ichancy"
    )
    async def create_player(self, player_name: str, password: str) -> IchancyResponse:
        """
        Create a new player account.
        
        Args:
            player_name: Unique player username
            password: Player password
            
        Returns:
            IchancyResponse with player data including generated username
        """
        logger.info(f"Creating Ichancy player: {player_name}")
        
        response = await self._request(
            "createPlayer",
            {"playerName": player_name, "password": password}
        )
        
        if response.success:
            logger.info(f"Created Ichancy player: {response.data}")
        else:
            logger.error(f"Failed to create player: {response.error}")
        
        return response
    
    @with_retry(
        max_retries=3,
        exceptions=(NetworkException, APITimeoutException),
        circuit_breaker_name="ichancy"
    )
    async def deposit(self, player_name: str, amount: float) -> IchancyResponse:
        """
        Deposit funds to player account.
        
        CRITICAL: This is a financial operation. Must be idempotent.
        
        Args:
            player_name: Ichancy username
            amount: Amount to deposit
            
        Returns:
            IchancyResponse with deposit confirmation
        """
        logger.info(f"Ichancy deposit: {player_name} <- {amount}")
        
        response = await self._request(
            "deposit",
            {"playerName": player_name, "amount": amount}
        )
        
        if response.success:
            logger.info(f"Deposit successful: {player_name} <- {amount}")
        else:
            logger.error(f"Deposit failed: {response.error}", player=player_name, amount=amount)
        
        return response
    
    @with_retry(
        max_retries=3,
        exceptions=(NetworkException, APITimeoutException),
        circuit_breaker_name="ichancy"
    )
    async def withdrawal(self, player_name: str, amount: float) -> IchancyResponse:
        """
        Withdraw funds from player account.
        
        CRITICAL: This is a financial operation. Must be idempotent.
        
        Args:
            player_name: Ichancy username
            amount: Amount to withdraw
            
        Returns:
            IchancyResponse with withdrawal confirmation
        """
        logger.info(f"Ichancy withdrawal: {player_name} -> {amount}")
        
        response = await self._request(
            "withdrawal",
            {"playerName": player_name, "amount": amount}
        )
        
        if response.success:
            logger.info(f"Withdrawal successful: {player_name} -> {amount}")
        else:
            logger.error(f"Withdrawal failed: {response.error}", player=player_name, amount=amount)
        
        return response
    
    @with_retry(
        max_retries=3,
        exceptions=(NetworkException, APITimeoutException),
        circuit_breaker_name="ichancy"
    )
    async def get_player_balance(self, player_name: str) -> IchancyResponse:
        """
        Get player's current balance.
        
        Args:
            player_name: Ichancy username
            
        Returns:
            IchancyResponse with balance data
        """
        response = await self._request(
            "get_player_balance",
            {"playerName": player_name},
            method="GET"
        )
        
        if response.success:
            logger.debug(f"Got balance for {player_name}: {response.data}")
        
        return response
    
    @with_retry(
        max_retries=3,
        exceptions=(NetworkException, APITimeoutException),
        circuit_breaker_name="ichancy"
    )
    async def check_agent_balance(self) -> IchancyResponse:
        """
        Get agent's current balance.
        
        Returns:
            IchancyResponse with agent balance
        """
        return await self._request("checkAgentBalance", method="GET")
    
    @with_retry(
        max_retries=2,
        exceptions=(NetworkException, APITimeoutException),
        circuit_breaker_name="ichancy"
    )
    async def change_password(self, player_name: str, new_password: str) -> IchancyResponse:
        """
        Change player's password.
        
        Args:
            player_name: Ichancy username
            new_password: New password
            
        Returns:
            IchancyResponse with confirmation
        """
        logger.info(f"Changing password for: {player_name}")
        
        return await self._request(
            "changePass",
            {"playerName": player_name, "password": new_password}
        )


# Global service instance
ichancy_service = IchancyService()
