#pip install pytelegrambotapi

import telebot

def app():
    bot = telebot.TeleBot('2083207800:AAFZ1QgWt4mYRv2Aw3gI-i2fmjvvDjZoqH4')

    @bot.message_handler(commands=['start'])
    def start_message(message):
        bot.send_message(message.chat.id, 'Бот в разработке, за Вами никто не приедет.')

    @bot.message_handler(content_types=['text'])
    def send_text(message):
        bot.send_message(message.chat.id, 'Говорю же, никто не приедет. Ждите запуска бота')

    bot.polling()

