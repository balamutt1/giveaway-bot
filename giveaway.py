import logging
import random
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

PRIZE, DESCRIPTION, WINNERS_COUNT, DURATION, CHANNEL = range(5)

giveaways = {}
participants = {}

async def is_channel_admin(bot, user_id, channel_id):
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return chat_member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == 'private':
        keyboard = [
            [InlineKeyboardButton("🎁 Начать розыгрыш", callback_data="start_giveaway")],
            [InlineKeyboardButton("📢 Создать в канале", callback_data="create_in_channel")]
        ]
        await update.message.reply_text(
            "Добро пожаловать в бота для розыгрышей!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def create_in_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎁 Введите название приза:")
    context.user_data['in_channel'] = True
    return PRIZE

async def start_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎁 Введите название приза:")
    context.user_data['in_channel'] = False
    return PRIZE

async def receive_prize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prize'] = update.message.text
    await update.message.reply_text("📝 Введите описание розыгрыша:")
    return DESCRIPTION

async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    await update.message.reply_text(
        "⏳ Введите длительность розыгрыша (например: 30s, 5m, 1h, 2d):\n\n"
        "Доступные форматы:\n"
        "s - секунды (например 30s)\n"
        "m - минуты (например 5m)\n"
        "h - часы (например 1h)\n"
        "d - дни (например 2d)"
    )
    return DURATION

async def receive_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    duration_str = update.message.text.lower()
    
    try:
        if not duration_str[:-1].isdigit():
            raise ValueError
        
        unit = duration_str[-1]
        value = int(duration_str[:-1])
        
        if unit not in ['s', 'm', 'h', 'd']:
            raise ValueError
        
        if unit == 's':
            duration = timedelta(seconds=value)
        elif unit == 'm':
            duration = timedelta(minutes=value)
        elif unit == 'h':
            duration = timedelta(hours=value)
        elif unit == 'd':
            duration = timedelta(days=value)
        
        context.user_data['end_time'] = datetime.now() + duration

        if context.user_data.get('in_channel', False):
            await update.message.reply_text("📢 Введите @username канала (например @my_channel):")
            return CHANNEL
        else:
            await update.message.reply_text("🔢 Введите количество победителей:")
            return WINNERS_COUNT
    
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат длительности. Пожалуйста, используйте формат:\n"
            "30s (30 секунд), 5m (5 минут), 1h (1 час) или 2d (2 дня)\n\n"
            "Попробуйте снова:"
        )
        return DURATION

async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_username = update.message.text.strip('@')
    context.user_data['channel'] = channel_username
    
    try:
        chat = await context.bot.get_chat(f"@{channel_username}")
        context.user_data['channel_id'] = chat.id
        
        if not await is_channel_admin(context.bot, update.message.from_user.id, chat.id):
            await update.message.reply_text("❌ Вы не являетесь администратором этого канала!")
            return ConversationHandler.END
            
        await update.message.reply_text("🔢 Введите количество победителей:")
        return WINNERS_COUNT
    except Exception as e:
        logger.error(f"Error getting channel info: {e}")
        await update.message.reply_text("❌ Не удалось найти канал. Проверьте правильность ввода.")
        return ConversationHandler.END

async def receive_winners_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        winners_count = int(update.message.text)
        if winners_count <= 0:
            raise ValueError
        
        giveaway_id = random.randint(1000, 9999)
        creator = update.message.from_user
        
        giveaways[giveaway_id] = {
            'prize': context.user_data['prize'],
            'description': context.user_data['description'],
            'winners_count': winners_count,
            'creator_id': creator.id,
            'end_time': context.user_data['end_time'],
            'message_id': None,
            'channel_id': context.user_data.get('channel_id'),
            'active': True
        }
        participants[giveaway_id] = []
        
        time_left = giveaways[giveaway_id]['end_time'] - datetime.now()
        time_str = format_time_left(time_left)
        
        keyboard = [
            [InlineKeyboardButton("✅ Участвовать", callback_data=f"join_{giveaway_id}")]
        ]
        
        if context.user_data.get('in_channel', False):
            channel_username = context.user_data.get('channel', '')
            try:
                message = await context.bot.send_message(
                    chat_id=giveaways[giveaway_id]['channel_id'],
                    text=f"🎉 <b>Новый розыгрыш!</b>\n\n"
                         f"🎁 Приз: {giveaways[giveaway_id]['prize']}\n"
                         f"📝 Описание: {giveaways[giveaway_id]['description']}\n"
                         f"🏆 Победителей: {giveaways[giveaway_id]['winners_count']}\n"
                         f"⏳ Окончание через: {time_str}\n"
                         f"👥 Участников: 0",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='HTML'
                )
                giveaways[giveaway_id]['message_id'] = message.message_id
                
                await update.message.reply_text(f"✅ Розыгрыш успешно создан в канале @{channel_username}!")
            except Exception as e:
                logger.error(f"Ошибка при публикации в канале: {e}")
                await update.message.reply_text("❌ Не удалось опубликовать розыгрыш в канале. Проверьте права бота.")
                return ConversationHandler.END
        else:
            message = await update.message.reply_text(
                f"🎉 <b>Новый розыгрыш!</b>\n\n"
                f"🎁 Приз: {giveaways[giveaway_id]['prize']}\n"
                f"📝 Описание: {giveaways[giveaway_id]['description']}\n"
                f"🏆 Победителей: {giveaways[giveaway_id]['winners_count']}\n"
                f"⏳ Окончание через: {time_str}\n"
                f"👥 Участников: 0",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            giveaways[giveaway_id]['message_id'] = message.message_id
        
        asyncio.create_task(end_giveaway_after_time(context, giveaway_id))
        
        return ConversationHandler.END
    
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите положительное число!")
        return WINNERS_COUNT

def format_time_left(time_left):
    hours, remainder = divmod(time_left.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    time_str = ""
    if time_left.days > 0:
        time_str += f"{time_left.days} д. "
    if hours > 0:
        time_str += f"{hours} ч. "
    if minutes > 0:
        time_str += f"{minutes} мин. "
    if seconds > 0:
        time_str += f"{seconds} сек."
    return time_str

async def end_giveaway_after_time(context: ContextTypes.DEFAULT_TYPE, giveaway_id: int):
    try:
        giveaway = giveaways.get(giveaway_id)
        if not giveaway:
            return
        
        time_left = (giveaway['end_time'] - datetime.now()).total_seconds()
        if time_left > 0:
            await asyncio.sleep(time_left)
        
        giveaway = giveaways.get(giveaway_id)
        if not giveaway or not giveaway['active']:
            return
        
        part = participants.get(giveaway_id, [])
        
        if len(part) >= giveaway['winners_count']:
            winners = random.sample(part, giveaway['winners_count'])
            winners_text = "\n".join(
                f"{i+1}. @{w['username']}" if w['username'] else f"{i+1}. {w['first_name']} (ID: {w['id']})"
                for i, w in enumerate(winners)
            )
            
            result_message = (
                f"🎉 <b>Розыгрыш завершен!</b>\n\n"
                f"🎁 Приз: {giveaway['prize']}\n"
                f"👥 Участников: {len(part)}\n\n"
                f"🏅 Победители:\n{winners_text}"
            )
            result_to_creator = (
                f"🏆 <b>Результаты розыгрыша:</b>\n\n"
                f"🎁 Приз: {giveaway['prize']}\n"
                f"👥 Участников: {len(part)}\n\n"
                f"🏅 Победители:\n{winners_text}"
            )
        else:
            result_message = (
                f"🎉 <b>Розыгрыш завершен!</b>\n\n"
                f"🎁 Приз: {giveaway['prize']}\n"
                f"👥 Участников: {len(part)}\n\n"
                f"❌ Недостаточно участников для выбора победителей!"
            )
            result_to_creator = (
                f"🏆 <b>Результаты розыгрыша:</b>\n\n"
                f"🎁 Приз: {giveaway['prize']}\n"
                f"👥 Участников: {len(part)}\n\n"
                f"❌ Недостаточно участников!"
            )
        
        try:
            if giveaway.get('channel_id'):
                await context.bot.edit_message_text(
                    chat_id=giveaway['channel_id'],
                    message_id=giveaway['message_id'],
                    text=result_message,
                    parse_mode='HTML'
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=giveaway['creator_id'],
                    message_id=giveaway['message_id'],
                    text=result_message,
                    parse_mode='HTML'
                )
            
            await context.bot.send_message(
                chat_id=giveaway['creator_id'],
                text=result_to_creator,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка при завершении розыгрыша: {e}")
        
        giveaway['active'] = False
    except Exception as e:
        logger.error(f"Ошибка в end_giveaway_after_time: {e}")

async def join_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    giveaway_id = int(query.data.split('_')[1])
    user = query.from_user
    
    if giveaway_id not in giveaways or not giveaways[giveaway_id]['active']:
        await query.answer("❌ Этот розыгрыш уже завершен!", show_alert=True)
        return
    
    if datetime.now() > giveaways[giveaway_id]['end_time']:
        await query.answer("❌ Время участия в розыгрыше истекло!", show_alert=True)
        return
    
    if user.id not in [p['id'] for p in participants[giveaway_id]]:
        participants[giveaway_id].append({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name
        })
        
        giveaway = giveaways[giveaway_id]
        time_left = giveaway['end_time'] - datetime.now()
        time_str = format_time_left(time_left)
        
        try:
            if giveaway.get('channel_id'):
                await context.bot.edit_message_text(
                    chat_id=giveaway['channel_id'],
                    message_id=giveaway['message_id'],
                    text=f"🎉 <b>Новый розыгрыш!</b>\n\n"
                         f"🎁 Приз: {giveaway['prize']}\n"
                         f"📝 Описание: {giveaway['description']}\n"
                         f"🏆 Победителей: {giveaway['winners_count']}\n"
                         f"⏳ Окончание через: {time_str}\n"
                         f"👥 Участников: {len(participants[giveaway_id])}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Участвовать", callback_data=f"join_{giveaway_id}")]
                    ])
                )
            else:
                await query.edit_message_text(
                    text=f"🎉 <b>Новый розыгрыш!</b>\n\n"
                         f"🎁 Приз: {giveaway['prize']}\n"
                         f"📝 Описание: {giveaway['description']}\n"
                         f"🏆 Победителей: {giveaway['winners_count']}\n"
                         f"⏳ Окончание через: {time_str}\n"
                         f"👥 Участников: {len(participants[giveaway_id])}",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Участвовать", callback_data=f"join_{giveaway_id}")]
                    ])
                )
            
            await context.bot.send_message(
                chat_id=user.id,
                text="✅ Вы успешно зарегистрировались в розыгрыше!"
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения: {e}")

async def draw_winners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    giveaway_id = int(query.data.split('_')[1])
    
    if giveaway_id not in giveaways or not giveaways[giveaway_id]['active']:
        await query.answer("❌ Этот розыгрыш уже завершен!", show_alert=True)
        return
    
    giveaway = giveaways[giveaway_id]
    
    if giveaway.get('channel_id'):
        is_admin = await is_channel_admin(context.bot, query.from_user.id, giveaway['channel_id'])
    else:
        is_admin = query.from_user.id == giveaway['creator_id']
    
    if not is_admin:
        await query.answer("❌ Только администратор может завершить розыгрыш!", show_alert=True)
        return
    
    part = participants[giveaway_id]
    
    if len(part) < giveaway['winners_count']:
        await query.answer(f"❌ Нужно минимум {giveaway['winners_count']} участников", show_alert=True)
        return
    
    winners = random.sample(part, giveaway['winners_count'])
    winners_text = "\n".join(
        f"{i+1}. @{w['username']}" if w['username'] else f"{i+1}. {w['first_name']} (ID: {w['id']})"
        for i, w in enumerate(winners)
    )
    
    result_message = (
        f"🎉 <b>Розыгрыш завершен!</b>\n\n"
        f"🎁 Приз: {giveaway['prize']}\n"
        f"👥 Участников: {len(part)}\n\n"
        f"🏅 Победители:\n{winners_text}"
    )
    
    try:
        if giveaway.get('channel_id'):
            await context.bot.edit_message_text(
                chat_id=giveaway['channel_id'],
                message_id=giveaway['message_id'],
                text=result_message,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                text=result_message,
                parse_mode='HTML'
            )
        
        await context.bot.send_message(
            chat_id=giveaway['creator_id'],
            text=f"🏆 <b>Результаты розыгрыша:</b>\n\n"
                 f"🎁 Приз: {giveaway['prize']}\n"
                 f"👥 Участников: {len(part)}\n\n"
                 f"🏅 Победители:\n{winners_text}",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка при завершении розыгрыша: {e}")
    
    giveaway['active'] = False

def main():
    application = ApplicationBuilder().token("YOUR_BOT_TOKEN").build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_giveaway, pattern='^start_giveaway$'),
            CallbackQueryHandler(create_in_channel, pattern='^create_in_channel$')
        ],
        states={
            PRIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prize)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_duration)],
            CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel)],
            WINNERS_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_winners_count)]
        },
        fallbacks=[]
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(join_giveaway, pattern='^join_'))
    application.add_handler(CallbackQueryHandler(draw_winners, pattern='^draw_'))
    
    application.run_polling()

if __name__ == '__main__':
    main()