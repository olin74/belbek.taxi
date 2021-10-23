
import redis
import telebot

def app():
    bot = telebot.TeleBot('2083207800:AAFZ1QgWt4mYRv2Aw3gI-i2fmjvvDjZoqH4')

    redis_data = redis.StrictRedis.from_url('redis://Z3rXtadcdy2nW0TIHXCCFP3J@ckv2rp80d000v0ub978gb171y:6379')
    cm = redis_data.get('count_start')


    @bot.message_handler(commands=['start'])
    def start_message(message):
        redis_data['count_start'] += 1
        bot.send_message(message.chat.id, f"Бот в разработке, за Вами никто не приедет. Запусков: {redis_data['count_start']}", )

    @bot.message_handler(content_types=['text'])
    def send_text(message):
        bot.send_message(message.chat.id, 'Говорю же, никто не приедет. Ждите запуска бота')

    bot.polling()

if __name__ == "__main__":
    app()
