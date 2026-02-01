"""
Flask admin routes for the dashboard.
"""
import asyncio
from datetime import datetime, timedelta
from flask import Blueprint, render_template_string, request, redirect, url_for, flash, session, jsonify

from config import config
from db import (
    db, User, Transaction, Payment, Bonus,
    TransactionType, TransactionState, PaymentState, UserState,
    UserRepository, TransactionRepository, PaymentRepository, BonusRepository
)
from services import ichancy_service, wallet_service, bonus_service
from admin.auth import login_required, authenticate_admin, is_logged_in
from utils.logger import get_logger

logger = get_logger("admin_routes")

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ============ Helper Functions ============

def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============ Templates ============

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Admin Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .flash { animation: fadeOut 5s forwards; }
        @keyframes fadeOut { 0% { opacity: 1; } 80% { opacity: 1; } 100% { opacity: 0; } }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    {% if logged_in %}
    <nav class="bg-gray-800 text-white p-4">
        <div class="container mx-auto flex justify-between items-center">
            <a href="{{ url_for('admin.dashboard') }}" class="text-xl font-bold">Finance Bot Admin</a>
            <div class="flex gap-4">
                <a href="{{ url_for('admin.dashboard') }}" class="hover:text-gray-300">Dashboard</a>
                <a href="{{ url_for('admin.users') }}" class="hover:text-gray-300">Users</a>
                <a href="{{ url_for('admin.transactions') }}" class="hover:text-gray-300">Transactions</a>
                <a href="{{ url_for('admin.payments') }}" class="hover:text-gray-300">Payments</a>
                <a href="{{ url_for('admin.bonuses') }}" class="hover:text-gray-300">Bonuses</a>
                <a href="{{ url_for('admin.logout') }}" class="text-red-400 hover:text-red-300">Logout</a>
            </div>
        </div>
    </nav>
    {% endif %}
    
    <main class="container mx-auto p-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        <div class="mb-4">
            {% for category, message in messages %}
            <div class="flash p-4 rounded {% if category == 'error' %}bg-red-100 text-red-700{% elif category == 'success' %}bg-green-100 text-green-700{% else %}bg-blue-100 text-blue-700{% endif %}">
                {{ message }}
            </div>
            {% endfor %}
        </div>
        {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </main>
</body>
</html>
"""

LOGIN_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="max-w-md mx-auto mt-20">
    <div class="bg-white p-8 rounded-lg shadow-md">
        <h1 class="text-2xl font-bold mb-6 text-center">Admin Login</h1>
        <form method="POST">
            <div class="mb-4">
                <label class="block text-gray-700 mb-2">Username</label>
                <input type="text" name="username" required 
                    class="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div class="mb-6">
                <label class="block text-gray-700 mb-2">Password</label>
                <input type="password" name="password" required
                    class="w-full p-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <button type="submit" 
                class="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700">
                Login
            </button>
        </form>
    </div>
</div>
{% endblock %}
"""

DASHBOARD_TEMPLATE = """
{% extends "base" %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">Dashboard</h1>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
    <div class="bg-white p-6 rounded-lg shadow">
        <h3 class="text-gray-500 text-sm">Total Users</h3>
        <p class="text-3xl font-bold">{{ stats.total_users }}</p>
    </div>
    <div class="bg-white p-6 rounded-lg shadow">
        <h3 class="text-gray-500 text-sm">Total Deposits</h3>
        <p class="text-3xl font-bold text-green-600">{{ "{:,.0f}".format(stats.total_deposits) }} SYP</p>
    </div>
    <div class="bg-white p-6 rounded-lg shadow">
        <h3 class="text-gray-500 text-sm">Total Withdrawals</h3>
        <p class="text-3xl font-bold text-red-600">{{ "{:,.0f}".format(stats.total_withdrawals) }} SYP</p>
    </div>
    <div class="bg-white p-6 rounded-lg shadow">
        <h3 class="text-gray-500 text-sm">Pending Payments</h3>
        <p class="text-3xl font-bold text-yellow-600">{{ stats.pending_payments }}</p>
    </div>
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div class="bg-white p-6 rounded-lg shadow">
        <h2 class="text-xl font-bold mb-4">Recent Transactions</h2>
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b">
                        <th class="text-left p-2">User</th>
                        <th class="text-left p-2">Type</th>
                        <th class="text-right p-2">Amount</th>
                        <th class="text-left p-2">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for txn in recent_transactions %}
                    <tr class="border-b hover:bg-gray-50">
                        <td class="p-2">{{ txn.user_id }}</td>
                        <td class="p-2">{{ txn.type.value }}</td>
                        <td class="p-2 text-right">{{ "{:,.0f}".format(txn.amount) }}</td>
                        <td class="p-2">
                            <span class="px-2 py-1 rounded text-xs
                                {% if txn.state.value == 'completed' %}bg-green-100 text-green-800
                                {% elif txn.state.value == 'pending' %}bg-yellow-100 text-yellow-800
                                {% else %}bg-red-100 text-red-800{% endif %}">
                                {{ txn.state.value }}
                            </span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    
    <div class="bg-white p-6 rounded-lg shadow">
        <h2 class="text-xl font-bold mb-4">API Status</h2>
        <div class="space-y-4">
            <div class="flex justify-between items-center p-3 bg-gray-50 rounded">
                <span>Ichancy API</span>
                <span id="ichancy-status" class="px-2 py-1 rounded text-xs bg-gray-200">Checking...</span>
            </div>
            <div class="flex justify-between items-center p-3 bg-gray-50 rounded">
                <span>Agent Balance</span>
                <span id="agent-balance" class="font-bold">Loading...</span>
            </div>
        </div>
        <script>
            fetch('{{ url_for("admin.api_status") }}')
                .then(r => r.json())
                .then(data => {
                    const statusEl = document.getElementById('ichancy-status');
                    const balanceEl = document.getElementById('agent-balance');
                    if (data.ichancy_online) {
                        statusEl.textContent = 'Online';
                        statusEl.className = 'px-2 py-1 rounded text-xs bg-green-100 text-green-800';
                    } else {
                        statusEl.textContent = 'Offline';
                        statusEl.className = 'px-2 py-1 rounded text-xs bg-red-100 text-red-800';
                    }
                    balanceEl.textContent = data.agent_balance ? data.agent_balance.toLocaleString() + ' SYP' : 'N/A';
                });
        </script>
    </div>
</div>
{% endblock %}
"""

USERS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">Users</h1>

<div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="w-full">
        <thead class="bg-gray-50">
            <tr>
                <th class="text-left p-4">ID</th>
                <th class="text-left p-4">Username</th>
                <th class="text-left p-4">Ichancy</th>
                <th class="text-right p-4">Balance</th>
                <th class="text-left p-4">Status</th>
                <th class="text-left p-4">Created</th>
                <th class="text-left p-4">Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for user in users %}
            <tr class="border-t hover:bg-gray-50">
                <td class="p-4">{{ user.id }}</td>
                <td class="p-4">@{{ user.telegram_username or 'N/A' }}</td>
                <td class="p-4">{{ user.ichancy_username or 'Not registered' }}</td>
                <td class="p-4 text-right font-mono">{{ "{:,.0f}".format(user.local_balance) }}</td>
                <td class="p-4">
                    <span class="px-2 py-1 rounded text-xs
                        {% if user.state.value == 'active' %}bg-green-100 text-green-800
                        {% else %}bg-red-100 text-red-800{% endif %}">
                        {{ user.state.value }}
                    </span>
                </td>
                <td class="p-4 text-sm text-gray-500">{{ user.created_at.strftime('%Y-%m-%d') }}</td>
                <td class="p-4">
                    <a href="{{ url_for('admin.user_detail', user_id=user.id) }}" 
                        class="text-blue-600 hover:underline">View</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

TRANSACTIONS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">Transactions</h1>

<div class="mb-4 flex gap-2">
    <a href="{{ url_for('admin.transactions') }}" 
        class="px-4 py-2 rounded {% if not filter %}bg-blue-600 text-white{% else %}bg-gray-200{% endif %}">All</a>
    <a href="{{ url_for('admin.transactions', filter='pending') }}"
        class="px-4 py-2 rounded {% if filter == 'pending' %}bg-blue-600 text-white{% else %}bg-gray-200{% endif %}">Pending</a>
    <a href="{{ url_for('admin.transactions', filter='completed') }}"
        class="px-4 py-2 rounded {% if filter == 'completed' %}bg-blue-600 text-white{% else %}bg-gray-200{% endif %}">Completed</a>
    <a href="{{ url_for('admin.transactions', filter='failed') }}"
        class="px-4 py-2 rounded {% if filter == 'failed' %}bg-blue-600 text-white{% else %}bg-gray-200{% endif %}">Failed</a>
</div>

<div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="w-full">
        <thead class="bg-gray-50">
            <tr>
                <th class="text-left p-4">ID</th>
                <th class="text-left p-4">User</th>
                <th class="text-left p-4">Type</th>
                <th class="text-right p-4">Amount</th>
                <th class="text-left p-4">Status</th>
                <th class="text-left p-4">Created</th>
                <th class="text-left p-4">Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for txn in transactions %}
            <tr class="border-t hover:bg-gray-50">
                <td class="p-4 font-mono text-sm">{{ txn.id[:8] }}...</td>
                <td class="p-4">{{ txn.user_id }}</td>
                <td class="p-4">
                    <span class="{% if txn.type.value == 'deposit' %}text-green-600{% else %}text-red-600{% endif %}">
                        {{ txn.type.value }}
                    </span>
                </td>
                <td class="p-4 text-right font-mono">{{ "{:,.0f}".format(txn.amount) }}</td>
                <td class="p-4">
                    <span class="px-2 py-1 rounded text-xs
                        {% if txn.state.value == 'completed' %}bg-green-100 text-green-800
                        {% elif txn.state.value == 'pending' %}bg-yellow-100 text-yellow-800
                        {% elif txn.state.value == 'processing' %}bg-blue-100 text-blue-800
                        {% else %}bg-red-100 text-red-800{% endif %}">
                        {{ txn.state.value }}
                    </span>
                </td>
                <td class="p-4 text-sm text-gray-500">{{ txn.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                <td class="p-4">
                    <a href="{{ url_for('admin.transaction_detail', txn_id=txn.id) }}"
                        class="text-blue-600 hover:underline">View</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

PAYMENTS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">Pending Withdrawals</h1>

<div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="w-full">
        <thead class="bg-gray-50">
            <tr>
                <th class="text-left p-4">ID</th>
                <th class="text-left p-4">User</th>
                <th class="text-left p-4">Provider</th>
                <th class="text-left p-4">Phone</th>
                <th class="text-right p-4">Amount</th>
                <th class="text-left p-4">Status</th>
                <th class="text-left p-4">Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for payment in payments %}
            <tr class="border-t hover:bg-gray-50">
                <td class="p-4 font-mono text-sm">{{ payment.id[:8] }}...</td>
                <td class="p-4">{{ payment.user_id }}</td>
                <td class="p-4">{{ payment.provider.value }}</td>
                <td class="p-4">{{ payment.phone_number or 'N/A' }}</td>
                <td class="p-4 text-right font-mono">{{ "{:,.0f}".format(payment.amount) }}</td>
                <td class="p-4">
                    <span class="px-2 py-1 rounded text-xs
                        {% if payment.state.value == 'verified' %}bg-green-100 text-green-800
                        {% elif payment.state.value == 'pending' %}bg-yellow-100 text-yellow-800
                        {% else %}bg-red-100 text-red-800{% endif %}">
                        {{ payment.state.value }}
                    </span>
                </td>
                <td class="p-4">
                    {% if payment.state.value == 'pending' and payment.phone_number %}
                    <form method="POST" action="{{ url_for('admin.process_payout', payment_id=payment.id) }}" class="inline">
                        <button type="submit" class="bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700">
                            Mark Paid
                        </button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

BONUSES_TEMPLATE = """
{% extends "base" %}
{% block content %}
<h1 class="text-3xl font-bold mb-6">Bonus Codes</h1>

<div class="mb-6 bg-white p-6 rounded-lg shadow">
    <h2 class="text-xl font-bold mb-4">Create New Bonus</h2>
    <form method="POST" action="{{ url_for('admin.create_bonus') }}" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div>
            <label class="block text-sm text-gray-600 mb-1">Code</label>
            <input type="text" name="code" required class="w-full p-2 border rounded">
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Description</label>
            <input type="text" name="description" class="w-full p-2 border rounded">
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Type</label>
            <select name="bonus_type" class="w-full p-2 border rounded">
                <option value="fixed">Fixed Amount</option>
                <option value="percentage">Percentage</option>
            </select>
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Value</label>
            <input type="number" name="value" required class="w-full p-2 border rounded">
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Min Deposit</label>
            <input type="number" name="min_deposit" value="0" class="w-full p-2 border rounded">
        </div>
        <div>
            <label class="block text-sm text-gray-600 mb-1">Max Uses (empty = unlimited)</label>
            <input type="number" name="max_uses" class="w-full p-2 border rounded">
        </div>
        <div class="md:col-span-2 lg:col-span-3">
            <button type="submit" class="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700">
                Create Bonus
            </button>
        </div>
    </form>
</div>

<div class="bg-white rounded-lg shadow overflow-hidden">
    <table class="w-full">
        <thead class="bg-gray-50">
            <tr>
                <th class="text-left p-4">Code</th>
                <th class="text-left p-4">Description</th>
                <th class="text-left p-4">Type</th>
                <th class="text-right p-4">Value</th>
                <th class="text-right p-4">Uses</th>
                <th class="text-left p-4">Status</th>
                <th class="text-left p-4">Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for bonus in bonuses %}
            <tr class="border-t hover:bg-gray-50">
                <td class="p-4 font-mono">{{ bonus.code }}</td>
                <td class="p-4">{{ bonus.description or '-' }}</td>
                <td class="p-4">{{ bonus.bonus_type }}</td>
                <td class="p-4 text-right">
                    {% if bonus.bonus_type == 'percentage' %}{{ bonus.value }}%{% else %}{{ "{:,.0f}".format(bonus.value) }}{% endif %}
                </td>
                <td class="p-4 text-right">{{ bonus.uses_count }}{% if bonus.max_uses %}/{{ bonus.max_uses }}{% endif %}</td>
                <td class="p-4">
                    <span class="px-2 py-1 rounded text-xs
                        {% if bonus.is_active %}bg-green-100 text-green-800{% else %}bg-gray-100 text-gray-800{% endif %}">
                        {% if bonus.is_active %}Active{% else %}Inactive{% endif %}
                    </span>
                </td>
                <td class="p-4">
                    {% if bonus.is_active %}
                    <form method="POST" action="{{ url_for('admin.deactivate_bonus', code=bonus.code) }}" class="inline">
                        <button type="submit" class="text-red-600 hover:underline">Deactivate</button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""


# ============ Template Rendering ============

def render(template: str, **kwargs) -> str:
    """Render template with base."""
    from jinja2 import Environment, BaseLoader
    from flask import get_flashed_messages, url_for
    
    env = Environment(loader=BaseLoader())
    env.globals.update(
        get_flashed_messages=get_flashed_messages,
        url_for=url_for
    )
    
    # Register base template
    base_tmpl = env.from_string(BASE_TEMPLATE)
    
    # Render child template
    child_tmpl = env.from_string(template.replace('{% extends "base" %}', ''))
    
    # Extract content block
    content = child_tmpl.render(**kwargs, logged_in=is_logged_in())
    
    # Render full page
    full_template = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', content)
    return env.from_string(full_template).render(**kwargs, logged_in=is_logged_in())


# ============ Routes ============

@admin_bp.route("/")
@login_required
def dashboard():
    """Admin dashboard."""
    async def get_data():
        # Get statistics
        async with db.connection() as conn:
            # Total users
            cursor = await conn.execute("SELECT COUNT(*) as count FROM users")
            row = await cursor.fetchone()
            total_users = row["count"] if row else 0
            
            # Total deposits
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = 'deposit' AND state = 'completed'"
            )
            row = await cursor.fetchone()
            total_deposits = row["total"] if row else 0
            
            # Total withdrawals
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions WHERE type = 'withdrawal' AND state = 'completed'"
            )
            row = await cursor.fetchone()
            total_withdrawals = row["total"] if row else 0
            
            # Pending payments (withdrawals)
            cursor = await conn.execute(
                "SELECT COUNT(*) as count FROM payments WHERE state = 'pending' AND phone_number IS NOT NULL"
            )
            row = await cursor.fetchone()
            pending_payments = row["count"] if row else 0
        
        # Recent transactions
        transactions = await TransactionRepository.get_pending_transactions()
        recent = transactions[:10] if transactions else []
        
        return {
            "stats": {
                "total_users": total_users,
                "total_deposits": total_deposits,
                "total_withdrawals": total_withdrawals,
                "pending_payments": pending_payments
            },
            "recent_transactions": recent
        }
    
    data = run_async(get_data())
    return render(DASHBOARD_TEMPLATE, title="Dashboard", **data)


@admin_bp.route("/api/status")
@login_required
def api_status():
    """Get API status."""
    async def check():
        try:
            status = await ichancy_service.check_status()
            balance_result = await ichancy_service.check_agent_balance()
            return {
                "ichancy_online": status.success,
                "agent_balance": balance_result.data.get("balance") if balance_result.success else None
            }
        except Exception:
            return {"ichancy_online": False, "agent_balance": None}
    
    return jsonify(run_async(check()))


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Admin login."""
    if is_logged_in():
        return redirect(url_for("admin.dashboard"))
    
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        
        if run_async(authenticate_admin(username or "", password or "")):
            session["admin_logged_in"] = True
            session["admin_username"] = username
            flash("Logged in successfully!", "success")
            
            next_url = request.args.get("next")
            return redirect(next_url or url_for("admin.dashboard"))
        else:
            flash("Invalid credentials.", "error")
    
    return render(LOGIN_TEMPLATE, title="Login")


@admin_bp.route("/logout")
def logout():
    """Admin logout."""
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.route("/users")
@login_required
def users():
    """List all users."""
    user_list = run_async(UserRepository.get_all(limit=100))
    return render(USERS_TEMPLATE, title="Users", users=user_list)


@admin_bp.route("/users/<int:user_id>")
@login_required
def user_detail(user_id: int):
    """User detail page."""
    user = run_async(UserRepository.get_by_id(user_id))
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin.users"))
    
    transactions = run_async(TransactionRepository.get_user_transactions(user_id))
    
    # Simple template for user detail
    template = """
    {% extends "base" %}
    {% block content %}
    <h1 class="text-3xl font-bold mb-6">User #{{ user.id }}</h1>
    <div class="bg-white p-6 rounded-lg shadow mb-6">
        <div class="grid grid-cols-2 gap-4">
            <div><span class="text-gray-500">Telegram:</span> @{{ user.telegram_username or 'N/A' }}</div>
            <div><span class="text-gray-500">Ichancy:</span> {{ user.ichancy_username or 'Not registered' }}</div>
            <div><span class="text-gray-500">Balance:</span> {{ "{:,.0f}".format(user.local_balance) }} SYP</div>
            <div><span class="text-gray-500">Status:</span> {{ user.state.value }}</div>
            <div><span class="text-gray-500">Total Deposited:</span> {{ "{:,.0f}".format(user.total_deposited) }} SYP</div>
            <div><span class="text-gray-500">Total Withdrawn:</span> {{ "{:,.0f}".format(user.total_withdrawn) }} SYP</div>
        </div>
    </div>
    <h2 class="text-xl font-bold mb-4">Transactions</h2>
    <div class="bg-white rounded-lg shadow">
        <table class="w-full">
            <thead class="bg-gray-50">
                <tr>
                    <th class="text-left p-3">Type</th>
                    <th class="text-right p-3">Amount</th>
                    <th class="text-left p-3">Status</th>
                    <th class="text-left p-3">Date</th>
                </tr>
            </thead>
            <tbody>
                {% for txn in transactions %}
                <tr class="border-t">
                    <td class="p-3">{{ txn.type.value }}</td>
                    <td class="p-3 text-right">{{ "{:,.0f}".format(txn.amount) }}</td>
                    <td class="p-3">{{ txn.state.value }}</td>
                    <td class="p-3">{{ txn.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endblock %}
    """
    return render(template, title=f"User #{user_id}", user=user, transactions=transactions)


@admin_bp.route("/transactions")
@login_required
def transactions():
    """List transactions."""
    filter_type = request.args.get("filter")
    
    async def get_transactions():
        async with db.connection() as conn:
            if filter_type:
                cursor = await conn.execute(
                    "SELECT * FROM transactions WHERE state = ? ORDER BY created_at DESC LIMIT 100",
                    (filter_type,)
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM transactions ORDER BY created_at DESC LIMIT 100"
                )
            rows = await cursor.fetchall()
            return [TransactionRepository._row_to_transaction(row) for row in rows]
    
    txn_list = run_async(get_transactions())
    return render(TRANSACTIONS_TEMPLATE, title="Transactions", transactions=txn_list, filter=filter_type)


@admin_bp.route("/transactions/<txn_id>")
@login_required
def transaction_detail(txn_id: str):
    """Transaction detail page."""
    txn = run_async(TransactionRepository.get_by_id(txn_id))
    if not txn:
        flash("Transaction not found.", "error")
        return redirect(url_for("admin.transactions"))
    
    template = """
    {% extends "base" %}
    {% block content %}
    <h1 class="text-3xl font-bold mb-6">Transaction Details</h1>
    <div class="bg-white p-6 rounded-lg shadow">
        <div class="grid grid-cols-2 gap-4">
            <div><span class="text-gray-500">ID:</span> <code>{{ txn.id }}</code></div>
            <div><span class="text-gray-500">User:</span> {{ txn.user_id }}</div>
            <div><span class="text-gray-500">Type:</span> {{ txn.type.value }}</div>
            <div><span class="text-gray-500">State:</span> {{ txn.state.value }}</div>
            <div><span class="text-gray-500">Amount:</span> {{ "{:,.0f}".format(txn.amount) }} SYP</div>
            <div><span class="text-gray-500">Created:</span> {{ txn.created_at.strftime('%Y-%m-%d %H:%M:%S') }}</div>
            {% if txn.error_message %}
            <div class="col-span-2"><span class="text-gray-500">Error:</span> <span class="text-red-600">{{ txn.error_message }}</span></div>
            {% endif %}
        </div>
    </div>
    {% endblock %}
    """
    return render(template, title="Transaction", txn=txn)


@admin_bp.route("/payments")
@login_required
def payments():
    """List pending withdrawal payments."""
    async def get_payments():
        async with db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM payments WHERE phone_number IS NOT NULL ORDER BY created_at DESC LIMIT 100"
            )
            rows = await cursor.fetchall()
            return [PaymentRepository._row_to_payment(row) for row in rows]
    
    payment_list = run_async(get_payments())
    return render(PAYMENTS_TEMPLATE, title="Payments", payments=payment_list)


@admin_bp.route("/payments/<payment_id>/process", methods=["POST"])
@login_required
def process_payout(payment_id: str):
    """Mark a withdrawal as paid."""
    async def process():
        payment = await PaymentRepository.get_by_id(payment_id)
        if not payment:
            return False, "Payment not found"
        
        if payment.state != PaymentState.PENDING:
            return False, "Payment already processed"
        
        await PaymentRepository.update_state(payment_id, PaymentState.VERIFIED)
        return True, "Payment marked as completed"
    
    success, message = run_async(process())
    flash(message, "success" if success else "error")
    return redirect(url_for("admin.payments"))


@admin_bp.route("/bonuses")
@login_required
def bonuses():
    """List bonus codes."""
    async def get_bonuses():
        async with db.connection() as conn:
            cursor = await conn.execute("SELECT * FROM bonuses ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [BonusRepository._row_to_bonus(row) for row in rows]
    
    bonus_list = run_async(get_bonuses())
    return render(BONUSES_TEMPLATE, title="Bonuses", bonuses=bonus_list)


@admin_bp.route("/bonuses/create", methods=["POST"])
@login_required
def create_bonus():
    """Create a new bonus code."""
    code = request.form.get("code", "").upper()
    description = request.form.get("description", "")
    bonus_type = request.form.get("bonus_type", "fixed")
    value = float(request.form.get("value", 0))
    min_deposit = float(request.form.get("min_deposit", 0))
    max_uses = request.form.get("max_uses")
    max_uses = int(max_uses) if max_uses else None
    
    try:
        run_async(bonus_service.create_bonus(
            code=code,
            description=description,
            bonus_type=bonus_type,
            value=value,
            min_deposit=min_deposit,
            max_uses=max_uses
        ))
        flash(f"Bonus code '{code}' created successfully!", "success")
    except Exception as e:
        flash(f"Failed to create bonus: {e}", "error")
    
    return redirect(url_for("admin.bonuses"))


@admin_bp.route("/bonuses/<code>/deactivate", methods=["POST"])
@login_required
def deactivate_bonus(code: str):
    """Deactivate a bonus code."""
    run_async(bonus_service.deactivate_bonus(code))
    flash(f"Bonus code '{code}' deactivated.", "success")
    return redirect(url_for("admin.bonuses"))
