"""
Telegram keyboard layouts for the bot.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

from db.models import PaymentProvider


class Keyboards:
    """Reusable keyboard layouts."""
    
    # ============ Main Menu ============
    
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Main menu keyboard matching schema."""
        keyboard = [
            [KeyboardButton("Ichancy ⚡")],
            [KeyboardButton("🧁 شحن رصيد في البوت"), KeyboardButton("🧁 سحب رصيد من البوت")],
            [KeyboardButton("💰 نظام الاحالات"), KeyboardButton("🎁 كود هدية")],
            [KeyboardButton("🎁 اهداء رصيد"), KeyboardButton("📩 تواصل معنا")],
            [KeyboardButton("🛡 رسالة للأدمن"), KeyboardButton("☁️ الشروحات")],
            [KeyboardButton("🗂 السجل"), KeyboardButton("📱 ichancy apk")],
            [KeyboardButton("🌐 تطبيق Vpn لتشغيل أقسام الموقع")],
            [KeyboardButton("🆓 اللغة المجانية")],
            [KeyboardButton("🆕 الجاكبوت")],
            [KeyboardButton("📜 الشروط والأحكام")],
            [KeyboardButton("🎉 البونصات والعروض الحالية ضمن (Thunder Bot)")],
            [KeyboardButton("⭐ دخول مباشر للألعاب")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def account_actions() -> ReplyKeyboardMarkup:
        """Account actions keyboard matching schema."""
        keyboard = [
            [KeyboardButton("سحب من حساب"), KeyboardButton("شحن حساب")],
            [KeyboardButton("💰 شحن كامل الرصيد")],
            [KeyboardButton("🏠 القائمة الرئيسية")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    @staticmethod
    def main_menu_button() -> ReplyKeyboardMarkup:
        """Just the main menu button."""
        keyboard = [[KeyboardButton("🏠 القائمة الرئيسية")]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    @staticmethod
    def main_menu_inline() -> InlineKeyboardMarkup:
        """Main menu as inline keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("💰 الرصيد", callback_data="menu:balance"),
                InlineKeyboardButton("💳 إيداع", callback_data="menu:deposit")
            ],
            [
                InlineKeyboardButton("💸 سحب", callback_data="menu:withdraw"),
                InlineKeyboardButton("🎮 العب", callback_data="menu:play")
            ],
            [
                InlineKeyboardButton("📜 السجل", callback_data="menu:history"),
                InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu:settings")
            ],
            [InlineKeyboardButton("❓ مساعدة", callback_data="menu:help")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Deposit Flow ============
    
    @staticmethod
    def deposit_amounts() -> InlineKeyboardMarkup:
        """Preset deposit amounts."""
        keyboard = [
            [
                InlineKeyboardButton("5,000", callback_data="deposit:amount:5000"),
                InlineKeyboardButton("10,000", callback_data="deposit:amount:10000"),
                InlineKeyboardButton("25,000", callback_data="deposit:amount:25000")
            ],
            [
                InlineKeyboardButton("50,000", callback_data="deposit:amount:50000"),
                InlineKeyboardButton("100,000", callback_data="deposit:amount:100000"),
                InlineKeyboardButton("مخصص", callback_data="deposit:amount:custom")
            ],
            [InlineKeyboardButton("« رجوع", callback_data="menu:main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def payment_providers() -> InlineKeyboardMarkup:
        """Payment provider selection."""
        keyboard = [
            [InlineKeyboardButton("📱 سيريتل كاش", callback_data="deposit:provider:syriatel_cash")],
            [InlineKeyboardButton("📱 شام كاش", callback_data="deposit:provider:sham_cash")],
            [InlineKeyboardButton("« رجوع", callback_data="deposit:back")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def payment_confirmation(payment_id: str) -> InlineKeyboardMarkup:
        """Payment confirmation buttons."""
        keyboard = [
            [InlineKeyboardButton("✅ لقد دفعت", callback_data=f"payment:verify:{payment_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"payment:cancel:{payment_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def payment_verification_retry(payment_id: str) -> InlineKeyboardMarkup:
        """Retry payment verification."""
        keyboard = [
            [InlineKeyboardButton("🔄 إعادة محاولة التحقق", callback_data=f"payment:verify:{payment_id}")],
            [InlineKeyboardButton("📞 الاتصال بالدعم", callback_data="support:payment")],
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"payment:cancel:{payment_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Withdrawal Flow ============
    
    @staticmethod
    def withdraw_amounts(balance: float) -> InlineKeyboardMarkup:
        """Withdrawal amount selection based on balance."""
        buttons = []
        
        # Add preset amounts that are <= balance
        presets = [5000, 10000, 25000, 50000, 100000]
        row = []
        for amount in presets:
            if amount <= balance:
                row.append(InlineKeyboardButton(
                    f"{amount:,}", 
                    callback_data=f"withdraw:amount:{amount}"
                ))
            if len(row) == 3:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        # Add "All" and "Custom" options
        buttons.append([
            InlineKeyboardButton("💯 الكل", callback_data=f"withdraw:amount:{int(balance)}"),
            InlineKeyboardButton("✏️ مخصص", callback_data="withdraw:amount:custom")
        ])
        
        buttons.append([InlineKeyboardButton("« رجوع", callback_data="menu:main")])
        
        return InlineKeyboardMarkup(buttons)
    
    @staticmethod
    def withdraw_providers() -> InlineKeyboardMarkup:
        """Withdrawal provider selection."""
        keyboard = [
            [InlineKeyboardButton("📱 سيريتل كاش", callback_data="withdraw:provider:syriatel_cash")],
            [InlineKeyboardButton("📱 شام كاش", callback_data="withdraw:provider:sham_cash")],
            [InlineKeyboardButton("« رجوع", callback_data="withdraw:back")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def withdraw_confirmation(amount: float, provider: str) -> InlineKeyboardMarkup:
        """Withdrawal confirmation."""
        keyboard = [
            [InlineKeyboardButton("✅ تأكيد السحب", callback_data="withdraw:confirm")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="withdraw:cancel")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Registration Flow ============
    
    @staticmethod
    def registration_start() -> InlineKeyboardMarkup:
        """Start registration prompt."""
        keyboard = [
            [InlineKeyboardButton("🎮 إنشاء حساب ألعاب", callback_data="register:start")],
            [InlineKeyboardButton("❌ ليس الآن", callback_data="register:skip")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def registration_confirm(username: str) -> InlineKeyboardMarkup:
        """Confirm registration details."""
        keyboard = [
            [InlineKeyboardButton("✅ تأكيد", callback_data="register:confirm")],
            [InlineKeyboardButton("🔄 تغيير اسم المستخدم", callback_data="register:change_username")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="register:cancel")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Settings ============
    
    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Settings menu."""
        keyboard = [
            [InlineKeyboardButton("🔐 تغيير كلمة المرور", callback_data="settings:password")],
            [InlineKeyboardButton("📱 تحديث الهاتف", callback_data="settings:phone")],
            [InlineKeyboardButton("🔔 الإشعارات", callback_data="settings:notifications")],
            [InlineKeyboardButton("« العودة للقائمة", callback_data="menu:main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ History ============
    
    @staticmethod
    def history_filters() -> InlineKeyboardMarkup:
        """Transaction history filters."""
        keyboard = [
            [
                InlineKeyboardButton("الكل", callback_data="history:filter:all"),
                InlineKeyboardButton("الإيداعات", callback_data="history:filter:deposit"),
                InlineKeyboardButton("السحوبات", callback_data="history:filter:withdrawal")
            ],
            [InlineKeyboardButton("« رجوع", callback_data="menu:main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def history_pagination(current_page: int, total_pages: int, filter_type: str) -> InlineKeyboardMarkup:
        """Transaction history pagination."""
        buttons = []
        
        nav_row = []
        if current_page > 1:
            nav_row.append(InlineKeyboardButton(
                "« السابق", 
                callback_data=f"history:page:{current_page - 1}:{filter_type}"
            ))
        
        nav_row.append(InlineKeyboardButton(
            f"{current_page}/{total_pages}",
            callback_data="history:noop"
        ))
        
        if current_page < total_pages:
            nav_row.append(InlineKeyboardButton(
                "التالي »",
                callback_data=f"history:page:{current_page + 1}:{filter_type}"
            ))
        
        buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("« رجوع", callback_data="menu:history")])
        
        return InlineKeyboardMarkup(buttons)
    
    # ============ Confirmation Dialogs ============
    
    @staticmethod
    def yes_no(action_prefix: str) -> InlineKeyboardMarkup:
        """Generic yes/no confirmation."""
        keyboard = [
            [
                InlineKeyboardButton("✅ نعم", callback_data=f"{action_prefix}:yes"),
                InlineKeyboardButton("❌ لا", callback_data=f"{action_prefix}:no")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def cancel_only(action: str) -> InlineKeyboardMarkup:
        """Cancel button only."""
        keyboard = [
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"{action}:cancel")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Bonus ============
    
    @staticmethod
    def bonus_prompt() -> InlineKeyboardMarkup:
        """Prompt to enter bonus code."""
        keyboard = [
            [InlineKeyboardButton("🎁 أدخل كود الهدية", callback_data="bonus:enter")],
            [InlineKeyboardButton("تخطي", callback_data="bonus:skip")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Play / Game Access ============
    
    @staticmethod
    def play_menu() -> InlineKeyboardMarkup:
        """Game access menu."""
        keyboard = [
            [InlineKeyboardButton("🎮 فتح اللعبة", url="https://ichancy.game")],
            [InlineKeyboardButton("📋 نسخ بيانات الاعتماد", callback_data="play:credentials")],
            [InlineKeyboardButton("🔄 مزامنة الرصيد", callback_data="play:sync")],
            [InlineKeyboardButton("« رجوع", callback_data="menu:main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ============ Support ============
    
    @staticmethod
    def support_menu() -> InlineKeyboardMarkup:
        """Support options."""
        keyboard = [
            [InlineKeyboardButton("💬 الاتصال بالدعم", url="https://t.me/support")],
            [InlineKeyboardButton("📖 الأسئلة الشائعة", callback_data="help:faq")],
            [InlineKeyboardButton("« رجوع", callback_data="menu:main")]
        ]
        return InlineKeyboardMarkup(keyboard)


# Convenience instance
keyboards = Keyboards()
