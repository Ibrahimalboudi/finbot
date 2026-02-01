"""
Telegram bot handlers for all user interactions.
"""
import re
import secrets
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

from config import config
from db import (
    db, User, UserState, PaymentProvider,
    UserRepository, TransactionRepository
)
from services import (
    wallet_service, ichancy_service, bonus_service,
    PaymentVerificationResult
)
from bot.keyboards import keyboards
from bot.middlewares import create_middleware_chain
from utils.logger import get_logger

logger = get_logger("handlers")


# Conversation states
(
    STATE_START,
    STATE_MAIN_MENU,
    STATE_ICHANCY_CHECK,
    STATE_REGISTER_NAME,
    STATE_ACCOUNT_VIEW,
    STATE_ACCOUNT_ACTIONS,
    # Keep old states for other flows if needed
    AWAITING_DEPOSIT_AMOUNT,
    AWAITING_DEPOSIT_PROVIDER,
    AWAITING_PAYMENT_CODE,
    AWAITING_WITHDRAW_AMOUNT,
    AWAITING_WITHDRAW_PROVIDER,
    AWAITING_WITHDRAW_PHONE,
    AWAITING_BONUS_CODE,
    AWAITING_REGISTRATION_USERNAME,
) = range(14)


# ============ Utility Functions ============

def get_user(context: ContextTypes.DEFAULT_TYPE) -> Optional[User]:
    """Get user from context."""
    return context.user_data.get("db_user")


def format_balance(amount: float) -> str:
    """Format balance for display."""
    return f"{amount:,.0f} SYP"


# ============ Command Handlers ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command."""
    await update.message.reply_text(
        "اهلا بك في بوت ⚡\nاختر من القائمة بالأسفل 👇",
        reply_markup=keyboards.main_menu()
    )
    return STATE_MAIN_MENU


async def ichancy_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Ichancy ⚡ menu button."""
    user = get_user(context)
    
    if not user.ichancy_registered:
        await update.message.reply_text(
            "❗️أنت غير مسجل بعد\nيرجى إدخال اسم المستخدم للتسجيل:",
            reply_markup=keyboards.cancel_only("register")
        )
        return STATE_REGISTER_NAME
    
    # Registered - Show Account Screen
    text = (
        f"الدخول: {user.ichancy_username}\n"
        f"الايميل: {user.ichancy_username}@thunder.com\n"
        f"كلمة السر: {user.ichancy_password or '********'}"
    )
    await update.message.reply_text(
        text,
        reply_markup=keyboards.account_actions()
    )
    return STATE_ACCOUNT_ACTIONS


async def register_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle name input for registration."""
    username = update.message.text.strip()
    
    if username == "🏠 القائمة الرئيسية":
        return await start_command(update, context)

    # Basic validation
    if not re.match(r'^[a-z0-9]{3,15}$', username.lower()):
        await update.message.reply_text(
            "اسم المستخدم غير صالح. استخدم 3-15 حرفًا (أحرف وأرقام فقط):"
        )
        return STATE_REGISTER_NAME
    
    user = get_user(context)
    password = secrets.token_urlsafe(8)
    
    try:
        # Register with Ichancy
        result = await ichancy_service.create_player(username, password)
        
        if not result.success:
            await update.message.reply_text(
                f"فشل التسجيل: {result.error}\nيرجى المحاولة مرة أخرى باسم مستخدم آخر:"
            )
            return STATE_REGISTER_NAME
            
        # Success
        user.ichancy_username = result.data.get("username", username)
        user.ichancy_password = password
        user.ichancy_registered = True
        await UserRepository.update(user)
        
        # Update context user data
        context.user_data["db_user"] = user
        
        await update.message.reply_text("✅ تم التسجيل بنجاح!")
        
        # Show Account Screen
        text = (
            f"الدخول: {user.ichancy_username}\n"
            f"الايميل: {user.ichancy_username}@thunder.com\n"
            f"كلمة السر: {user.ichancy_password}"
        )
        await update.message.reply_text(
            text,
            reply_markup=keyboards.account_actions()
        )
        return STATE_ACCOUNT_ACTIONS
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        await update.message.reply_text("حدث خطأ أثناء التسجيل. يرجى المحاولة لاحقاً.")
        return STATE_MAIN_MENU

async def main_menu_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to main menu."""
    return await start_command(update, context)


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /balance command and Balance button."""
    user = get_user(context)
    
    # Get balances
    try:
        balances = await wallet_service.get_balance(user.id)
        
        text = (
            "💰 *رصيدك*\n\n"
            f"المحفظة المحلية: *{format_balance(balances['local_balance'])}*\n"
        )
        
        if balances.get("ichancy_balance") is not None:
            text += f"رصيد اللعبة: *{format_balance(balances['ichancy_balance'])}*\n"
        
        text += (
            f"\n📊 *الإحصائيات*\n"
            f"إجمالي الإيداع: {format_balance(balances['total_deposited'])}\n"
            f"إجمالي السحب: {format_balance(balances['total_withdrawn'])}"
        )
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=keyboards.main_menu_inline()
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=keyboards.main_menu()
            )
            
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        error_text = "عذراً، تعذر جلب رصيدك. يرجى المحاولة مرة أخرى."
        if update.callback_query:
            await update.callback_query.answer(error_text, show_alert=True)
        else:
            await update.message.reply_text(error_text)
    
    return STATE_MAIN_MENU


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /help command."""
    text = (
        "❓ *المساعدة والدعم*\n\n"
        "*الأوامر:*\n"
        "/start - بدء البوت\n"
        "/balance - تحقق من رصيدك\n"
        "/deposit - إجراء إيداع\n"
        "/withdraw - إجراء سحب\n"
        "/history - عرض سجل المعاملات\n"
        "/help - إظهار هذه المساعدة\n\n"
        "*كيفية الإيداع:*\n"
        "1. اختر مبلغ الإيداع\n"
        "2. اختر طريقة الدفع (سيريتل كاش/شام كاش)\n"
        "3. قم بالتحويل إلى رقمنا\n"
        "4. أدخل رمز التحويل\n"
        "5. سيتم إضافة الأموال إلى حسابك\n\n"
        "*كيفية السحب:*\n"
        "1. اختر مبلغ السحب\n"
        "2. اختر طريقة الدفع\n"
        "3. أدخل رقم هاتفك\n"
        "4. أكد السحب\n"
        "5. استلم الأموال في غضون 24 ساعة\n\n"
        "للدعم، تواصل مع @support"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboards.support_menu()
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown"
        )
    
    return STATE_MAIN_MENU


# ============ Deposit Flow ============

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start deposit flow."""
    user = get_user(context)
    
    if not user.ichancy_registered:
        text = "تحتاج إلى إنشاء حساب ألعاب أولاً."
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text, reply_markup=keyboards.registration_start())
        return STATE_MAIN_MENU
    
    text = (
        "💳 *إجراء إيداع*\n\n"
        f"الرصيد الحالي: {format_balance(user.local_balance)}\n\n"
        "اختر أو أدخل المبلغ الذي تريد إيداعه:"
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboards.deposit_amounts()
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboards.deposit_amounts()
        )
    
    return AWAITING_DEPOSIT_AMOUNT


async def deposit_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle deposit amount selection."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    if len(data) < 3:
        return AWAITING_DEPOSIT_AMOUNT
    
    amount_str = data[2]
    
    if amount_str == "custom":
        await query.edit_message_text(
            "أدخل المبلغ الذي تريد إيداعه (الحد الأدنى 1,000 ل.س):",
            reply_markup=keyboards.cancel_only("deposit")
        )
        return AWAITING_DEPOSIT_AMOUNT
    
    try:
        amount = float(amount_str)
        context.user_data["deposit_amount"] = amount
        
        await query.edit_message_text(
            f"المبلغ: *{format_balance(amount)}*\n\n"
            "اختر طريقة الدفع:",
            parse_mode="Markdown",
            reply_markup=keyboards.payment_providers()
        )
        return AWAITING_DEPOSIT_PROVIDER
        
    except ValueError:
        await query.edit_message_text(
            "مبلغ غير صالح. يرجى المحاولة مرة أخرى:",
            reply_markup=keyboards.deposit_amounts()
        )
        return AWAITING_DEPOSIT_AMOUNT


async def deposit_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom deposit amount input."""
    try:
        amount = float(update.message.text.replace(",", "").replace(" ", ""))
        
        if amount < 1000:
            await update.message.reply_text(
                "الحد الأدنى للإيداع هو 1,000 ل.س. يرجى إدخال مبلغ أكبر:"
            )
            return AWAITING_DEPOSIT_AMOUNT
        
        if amount > 10000000:
            await update.message.reply_text(
                "الحد الأقصى للإيداع هو 10,000,000 ل.س. يرجى إدخال مبلغ أصغر:"
            )
            return AWAITING_DEPOSIT_AMOUNT
        
        context.user_data["deposit_amount"] = amount
        
        await update.message.reply_text(
            f"المبلغ: *{format_balance(amount)}*\n\n"
            "اختر طريقة الدفع:",
            parse_mode="Markdown",
            reply_markup=keyboards.payment_providers()
        )
        return AWAITING_DEPOSIT_PROVIDER
        
    except ValueError:
        await update.message.reply_text(
            "يرجى إدخال رقم صالح:"
        )
        return AWAITING_DEPOSIT_AMOUNT

async def deposit_provider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment provider selection."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    if len(data) < 3:
        return AWAITING_DEPOSIT_PROVIDER
    
    provider_val = data[2]
    try:
        provider = PaymentProvider(provider_val)
    except ValueError:
        return AWAITING_DEPOSIT_PROVIDER
    
    amount = context.user_data.get("deposit_amount")
    if not amount:
        return await deposit_start(update, context)
    
    # Get payment instructions
    payment_number = "0930000000" if provider == PaymentProvider.SYRIATEL_CASH else "0990000000"
    
    # Create pending transaction
    user = get_user(context)
    txn = await wallet_service.create_deposit_transaction(
        user_id=user.id,
        amount=amount,
        provider=provider
    )
    context.user_data["pending_transaction_id"] = txn.id
    
    text = (
        f"💳 *إيداع: {provider.name.replace('_', ' ').title()}*\n\n"
        f"المبلغ المراد تحويله: *{format_balance(amount)}*\n"
        f"التحويل إلى رقم: `{payment_number}`\n\n"
        "بعد التحويل، يرجى إدخال *رمز التحويل* (معرف المعاملة) الذي استلمته في الرسالة النصية:"
    )
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only("payment")
    )
    return AWAITING_PAYMENT_CODE


async def payment_code_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle payment code input."""
    code = update.message.text.strip()
    txn_id = context.user_data.get("pending_transaction_id")
    
    if not txn_id:
        await update.message.reply_text("انتهت صلاحية الجلسة. يرجى البدء من جديد.")
        return await start_command(update, context)
    
    await update.message.reply_text("⏳ جاري التحقق من دفعتك... يرجى الانتظار.")
    
    try:
        # Verify payment
        result = await wallet_service.verify_and_complete_deposit(txn_id, code)
        
        if result.success:
            await update.message.reply_text(
                "✅ *تم التحقق من الدفع!*\n\n"
                f"تم إضافة الأموال إلى حسابك.\n"
                f"الرصيد الجديد: *{format_balance(result.new_balance)}*",
                parse_mode="Markdown",
                reply_markup=keyboards.main_menu()
            )
            # Clear session
            context.user_data.pop("deposit_amount", None)
            context.user_data.pop("pending_transaction_id", None)
            return STATE_MAIN_MENU
        else:
            await update.message.reply_text(
                f"❌ *فشل التحقق*\n\n"
                f"السبب: {result.error}\n\n"
                "يرجى التحقق من الرمز والمحاولة مرة أخرى، أو الاتصال بالدعم:",
                parse_mode="Markdown",
                reply_markup=keyboards.payment_failed_options()
            )
            return AWAITING_PAYMENT_CODE
            
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        await update.message.reply_text("حدث خطأ أثناء التحقق. يرجى المحاولة مرة أخرى لاحقاً.")
        return STATE_MAIN_MENU


# ============ Withdrawal Flow ============

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start withdrawal flow."""
    user = get_user(context)
    
    if not user.ichancy_registered:
        text = "تحتاج إلى إنشاء حساب ألعاب أولاً."
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        else:
            await update.message.reply_text(text, reply_markup=keyboards.registration_start())
        return STATE_MAIN_MENU
    
    # Sync balance first
    await update.message.reply_text("⏳ جاري مزامنة رصيد اللعبة...")
    try:
        balances = await wallet_service.get_balance(user.id)
        ichancy_balance = balances.get("ichancy_balance", 0)
        
        if ichancy_balance < 1000:
            await update.message.reply_text(
                f"رصيد اللعبة الخاص بك ({format_balance(ichancy_balance)}) أقل من الحد الأدنى لمبلغ السحب (1,000 ل.س).",
                reply_markup=keyboards.main_menu()
            )
            return STATE_MAIN_MENU
            
        text = (
            "💸 *سحب الأموال*\n\n"
            f"متاح للسحب: *{format_balance(ichancy_balance)}*\n\n"
            "اختر أو أدخل المبلغ الذي تريد سحبه:"
        )
        
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboards.withdraw_amounts()
        )
        return AWAITING_WITHDRAW_AMOUNT
        
    except Exception as e:
        logger.error(f"Error starting withdrawal: {e}")
        await update.message.reply_text("تعذر الوصول إلى حساب اللعبة الخاص بك. يرجى المحاولة مرة أخرى لاحقاً.")
        return STATE_MAIN_MENU


async def withdraw_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle withdrawal amount selection."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    amount_str = data[2]
    
    if amount_str == "custom":
        await query.edit_message_text(
            "أدخل المبلغ الذي تريد سحبه:",
            reply_markup=keyboards.cancel_only("withdraw")
        )
        return AWAITING_WITHDRAW_AMOUNT
    
    try:
        amount = float(amount_str)
        context.user_data["withdraw_amount"] = amount
        
        await query.edit_message_text(
            f"مبلغ السحب: *{format_balance(amount)}*\n\n"
            "اختر مكان استلام الأموال:",
            parse_mode="Markdown",
            reply_markup=keyboards.withdraw_providers()
        )
        return AWAITING_WITHDRAW_PROVIDER
    except ValueError:
        return AWAITING_WITHDRAW_AMOUNT


async def withdraw_amount_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom withdrawal amount input."""
    try:
        amount = float(update.message.text.replace(",", "").replace(" ", ""))
        user = get_user(context)
        
        if amount < 1000:
            await update.message.reply_text("الحد الأدنى للسحب هو 1,000 ل.س.")
            return AWAITING_WITHDRAW_AMOUNT
            
        context.user_data["withdraw_amount"] = amount
        
        await update.message.reply_text(
            f"مبلغ السحب: *{format_balance(amount)}*\n\n"
            "اختر مكان استلام الأموال:",
            parse_mode="Markdown",
            reply_markup=keyboards.withdraw_providers()
        )
        return AWAITING_WITHDRAW_PROVIDER
    except ValueError:
        await update.message.reply_text("يرجى إدخال رقم صالح:")
        return AWAITING_WITHDRAW_AMOUNT


async def withdraw_provider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle withdrawal provider selection."""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(":")
    provider = data[2]
    context.user_data["withdraw_provider"] = provider
    
    await query.edit_message_text(
        f"يرجى إدخال رقم هاتف *{provider.replace('_', ' ').title()}* الخاص بك لاستلام الأموال:",
        parse_mode="Markdown",
        reply_markup=keyboards.cancel_only("withdraw")
    )
    return AWAITING_WITHDRAW_PHONE


async def withdraw_phone_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle withdrawal phone number input."""
    phone = update.message.text.strip()
    
    if not re.match(r'^09[3-9][0-9]{7}$', phone):
        await update.message.reply_text("رقم هاتف غير صالح. يرجى إدخال رقم جوال سوري صالح (مثال: 0930000000):")
        return AWAITING_WITHDRAW_PHONE
    
    amount = context.user_data.get("withdraw_amount")
    provider = context.user_data.get("withdraw_provider")
    
    await update.message.reply_text(
        "⏳ جاري معالجة طلب السحب الخاص بك... يرجى الانتظار."
    )
    
    try:
        user = get_user(context)
        result = await wallet_service.process_withdrawal(
            user_id=user.id,
            amount=amount,
            provider=PaymentProvider(provider),
            phone=phone
        )
        
        if result.success:
            await update.message.reply_text(
                "✅ *تم طلب السحب!*\n\n"
                f"المبلغ: *{format_balance(amount)}*\n"
                f"إلى: {phone} ({provider.replace('_', ' ').title()})\n\n"
                "جاري معالجة طلبك. سيتم إرسال الأموال قريباً.",
                parse_mode="Markdown",
                reply_markup=keyboards.main_menu()
            )
            return STATE_MAIN_MENU
        else:
            await update.message.reply_text(
                f"❌ *فشل السحب*\n\n"
                f"السبب: {result.error}",
                parse_mode="Markdown",
                reply_markup=keyboards.main_menu()
            )
            return STATE_MAIN_MENU
            
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        await update.message.reply_text("حدث خطأ. يرجى المحاولة مرة أخرى لاحقاً.")
        return STATE_MAIN_MENU


# ============ History & Other ============

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View transaction history."""
    user = get_user(context)
    txns = await TransactionRepository.get_by_user_id(user.id, limit=10)
    
    if not txns:
        text = "ليس لديك أي معاملات بعد."
    else:
        text = "📜 *المعاملات الأخيرة*\n\n"
        for t in txns:
            icon = "➕" if t.type.value == "deposit" else "➖"
            date = t.created_at.strftime("%Y-%m-%d %H:%M")
            text += f"{icon} {format_balance(t.amount)} - {t.state.value.title()}\n"
            text += f"└ _{date}_ \n\n"
            
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboards.main_menu_inline()
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=keyboards.main_menu()
        )
    return STATE_MAIN_MENU


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current operation."""
    # Clear session data
    keys_to_clear = [
        "deposit_amount", "pending_payment_id", "pending_transaction_id",
        "withdraw_amount", "withdraw_provider", "suggested_username"
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)
    
    text = "تم الإلغاء. يمكنك الاختيار من القائمة:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            reply_markup=keyboards.main_menu_inline()
        )
    else:
        await update.message.reply_text(text, reply_markup=keyboards.main_menu())
    
    return STATE_MAIN_MENU


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle main menu callbacks."""
    query = update.callback_query
    await query.answer()
    
    action = query.data.split(":")[1] if ":" in query.data else ""
    
    if action == "main":
        await query.edit_message_text(
            "ماذا تريد أن تفعل؟",
            reply_markup=keyboards.main_menu_inline()
        )
        return STATE_MAIN_MENU
    elif action == "balance":
        return await balance_command(update, context)
    elif action == "deposit":
        return await deposit_start(update, context)
    elif action == "withdraw":
        return await withdraw_start(update, context)
    elif action == "history":
        return await history_command(update, context)
    elif action == "help":
        return await help_command(update, context)
    elif action == "settings":
        await query.edit_message_text(
            "⚙️ *الإعدادات*",
            parse_mode="Markdown",
            reply_markup=keyboards.settings_menu()
        )
        return STATE_MAIN_MENU
    
    return STATE_MAIN_MENU


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Route text messages based on button text."""
    text = update.message.text
    
    # Arabic mappings from keyboards.py
    if text == "Ichancy ⚡":
        return await ichancy_menu_handler(update, context)
    elif text == "🧁 شحن رصيد في البوت" or text == "شحن حساب":
        return await deposit_start(update, context)
    elif text == "🧁 سحب رصيد من البوت" or text == "سحب من حساب":
        return await withdraw_start(update, context)
    elif text == "🗂 السجل":
        return await history_command(update, context)
    elif text == "📩 تواصل معنا" or text == "❓ Help":
        return await help_command(update, context)
    elif text == "🏠 القائمة الرئيسية":
        return await start_command(update, context)
    
    return STATE_MAIN_MENU


def setup_handlers(application: Application) -> None:
    """Setup all bot handlers."""
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", create_middleware_chain(start_command)),
            MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(text_router)),
        ],
        states={
            STATE_MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(text_router)),
                CallbackQueryHandler(create_middleware_chain(menu_callback), pattern=r"^menu:"),
            ],
            STATE_REGISTER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(register_name_handler)),
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^register:cancel$"),
            ],
            STATE_ACCOUNT_ACTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(text_router)),
                CallbackQueryHandler(create_middleware_chain(menu_callback), pattern=r"^menu:"),
            ],
            AWAITING_DEPOSIT_AMOUNT: [
                CallbackQueryHandler(create_middleware_chain(deposit_amount_callback), pattern=r"^deposit:amount:"),
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^deposit:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(deposit_amount_text)),
            ],
            AWAITING_DEPOSIT_PROVIDER: [
                CallbackQueryHandler(create_middleware_chain(deposit_provider_callback), pattern=r"^deposit:provider:"),
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^deposit:(back|cancel)$"),
            ],
            AWAITING_PAYMENT_CODE: [
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^payment:cancel:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(payment_code_text)),
            ],
            AWAITING_WITHDRAW_AMOUNT: [
                CallbackQueryHandler(create_middleware_chain(withdraw_amount_callback), pattern=r"^withdraw:amount:"),
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^withdraw:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(withdraw_amount_text)),
            ],
            AWAITING_WITHDRAW_PROVIDER: [
                CallbackQueryHandler(create_middleware_chain(withdraw_provider_callback), pattern=r"^withdraw:provider:"),
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^withdraw:(back|cancel)$"),
            ],
            AWAITING_WITHDRAW_PHONE: [
                CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^withdraw:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_middleware_chain(withdraw_phone_text)),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", create_middleware_chain(cancel)),
            CallbackQueryHandler(create_middleware_chain(cancel), pattern=r"^.*:cancel$"),
        ],
        allow_reentry=True,
    )
    
    application.add_handler(conv_handler)
