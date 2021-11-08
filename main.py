import math
import redis
import telebot
from telebot import types
import time
import datetime
import re
import os

# Загружаем секретные ссылки и токены из системы
REDIS_URL = os.environ['REDIS_URL']
TELE_TOKEN = os.environ['TELEGRAM_TOKEN']
SYMBOL = "₽"

# Устанавливаем константы
ADMIN_LIST = [665812965]  # Список админов для спец команд (тут только Олин)
ABOUT_LIMIT = 100  # Лимит символов в объявлении
CONTENT_TYPES = ["text", "audio", "document", "photo", "sticker", "video", "video_note", "voice", "location", "contact",
                 "new_chat_members", "left_chat_member", "new_chat_title", "new_chat_photo", "delete_chat_photo",
                 "group_chat_created", "supergroup_chat_created", "channel_chat_created", "migrate_to_chat_id",
                 "migrate_from_chat_id", "pinned_message"]


# Вычисление расстояния между координатами
def get_distance(lat1, long1, lat2, long2):
    # Функция вычисления гаверсинуса
    def hav(x):
        return (math.sin(x / 2)) ** 2

    # Радиус текущей планеты в км, погрешность 0.5%
    planet_radius = 6371
    # Координаты из градусов в радианы
    long1_rad = math.pi * long1 / 180
    lat1_rad = math.pi * lat1 / 180
    long2_rad = math.pi * long2 / 180
    lat2_rad = math.pi * lat2 / 180
    # Много геоматематики, пояснять не буду.
    res = 2 * planet_radius * math.asin(math.sqrt(hav(long2_rad - long1_rad) + math.cos(long1_rad) *
                                                  math.cos(long1_rad) * hav(lat2_rad - lat1_rad)))
    return res


class Taxi:
    def __init__(self):
        redis_url = REDIS_URL
        # redis_url = 'redis://:@localhost:6379'  # Для теста на локальном сервере

        # База данных водителей
        self.drivers = {'about': redis.from_url(redis_url, db=1),
                        'radius': redis.from_url(redis_url, db=2),
                        'price': redis.from_url(redis_url, db=3),
                        'wait': redis.from_url(redis_url, db=4),
                        'status': redis.from_url(redis_url, db=5),
                        'geo_long': redis.from_url(redis_url, db=6),
                        'geo_lat': redis.from_url(redis_url, db=7),
                        'impressions': redis.from_url(redis_url, db=8),
                        'last_impression': redis.from_url(redis_url, db=9),
                        'views': redis.from_url(redis_url, db=10),
                        'name': redis.from_url(redis_url, db=11),
                        'username': redis.from_url(redis_url, db=12)}

        self.menu_items = ['👍 Поиск машины', '🚖 Я водитель']
        self.menu_car_items = ['Изменить объявление', 'Изменить радиус', 'Изменить цену за км', 'Выход',
                               'Пополнить баланс',
                               'Поддержка', "🚖 Поиск пассажиров"]
        self.menu_stop = "⛔️ Прекратить поиск ⛔️"
        self.menu_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        self.menu_keyboard.row(types.KeyboardButton(text=self.menu_items[0], request_location=True),
                               types.KeyboardButton(text=self.menu_items[1]))

    # Среднее значение среди водителей по произвольному полю
    def get_avg(self, field: str):
        tot = 0
        count = 0
        for k in self.drivers[field].keys():
            tot += int(self.drivers[field][k])
            count += 1
        if count == 0:
            return 0
        return int(tot / count)

    # Стартовое сообщение
    def go_start(self, bot, message):
        username = message.chat.id

        # Сброс статуса "в поиске пассажира" и ожидания ввода текста
        self.drivers['status'][username] = -1
        self.drivers['wait'][username] = -1
        # Подсчет статистики водителей (всего и активных), а также пассажиров в поиске
        total = 0
        active = 0

        for dr in self.drivers['status'].keys():
            total += 1
            if int(self.drivers['status'][dr]) == 1:
                active += 1
        menu_message = f"Водителей зарегистрировано: {total}\nСейчас активно: {active}\n" \
                       f"Канал поддержки: https://t.me/BelbekTaxi\n\n" \
                       f"Нажмите “{self.menu_items[0]}”" \
                       f" (геолокация на телефоне должна быть включена)" \
                       f" или пришлите свои координаты текстом через запятую." \
                       f" Бот предложит связаться с водителями возле Вас."
        bot.send_message(message.chat.id, menu_message, reply_markup=self.menu_keyboard, disable_web_page_preview=True)

    # Запрос объявления
    def go_about(self, bot, message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.id
        # Устанавливаем ожидание текстового ответа для поля "объявление"
        self.drivers['wait'][username] = 0
        bot.send_message(message.chat.id, f"Расскажите немного о себе и машине (не больше {ABOUT_LIMIT} символов),"
                                          f" например: “Ильдар. Синяя Хонда. Вожу быстро, но аккуратно.”"
                                          f" Для отмены введите /cancel",
                         reply_markup=keyboard)
        return

    # Запрос радиуса поиска
    def go_radius(self, bot, message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.id
        # Устанавливаем ожидание текстового ответа для радиуса (числового на самом деле, но проверим это позже)
        self.drivers['wait'][username] = 1
        avg_km = self.get_avg('radius')
        bot.send_message(message.chat.id, f"Задайте расстояние в километрах на которое вы готовы поехать за пассажиром."
                                          f"\nСреднее среди водителей: {avg_km}. Для отмены введите /cancel",
                         reply_markup=keyboard)
        return

    # Запрос оцены за км
    def go_price(self, bot, message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.id
        # Устанавливаем ожидание текстового ответа для цены(числового на самом деле, но проверим это позже)
        self.drivers['wait'][username] = 2
        avg_price = self.get_avg('price')
        bot.send_message(message.chat.id, f"Напишите сколько {SYMBOL} обычно вы берёте за километр пути (примерно)."
                                          f"\nСреднее среди водителей: {avg_price}. Для отмены введите /cancel",
                         reply_markup=keyboard)
        return

    # Формирование описания профиля водителя
    def get_profile(self, username):
        info_about = "Поле не заполнено"
        if username in self.drivers['about']:
            info_about = self.drivers['about'][username].decode("utf-8")
        info_radius = "Поле не заполнено"
        if username in self.drivers['radius']:
            info_radius = f"{int(self.drivers['radius'][username])} км"
        info_price = "Поле не заполнено"
        if username in self.drivers['price']:
            info_price = f"{int(self.drivers['price'][username])} {SYMBOL}/км"
        impressions = 0
        if username in self.drivers['impressions']:
            # Проверка на смену дня и сброс счетчика
            dt_timestamp = int(datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0)).timestamp())
            if int(self.drivers['last_impression'][username]) < dt_timestamp:
                self.drivers['impressions'][username] = 0
                current_time = int(time.time())
                self.drivers['last_impression'][username] = current_time
            impressions = int(self.drivers['impressions'][username])
        balance = 0
        if username in self.drivers['views']:
            balance = int(self.drivers['views'][username])

        info = f"Объявление: {info_about}\nОриентировочная цена: {info_price}\nРадиус поиска: {info_radius}\n" \
               f"Показов сегодня: {impressions}" \
               f"\nПоказов всего: {balance}"
        return info

    # Меню водителя
    def go_menu_car(self, bot, message):
        username = message.chat.id
        menu_car = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        # menu_car.add(self.menu_car_items[i] for i in range(4))
        menu_car.row(types.KeyboardButton(text=self.menu_car_items[0]),
                     types.KeyboardButton(text=self.menu_car_items[1]))
        menu_car.row(types.KeyboardButton(text=self.menu_car_items[2]),
                     types.KeyboardButton(text=self.menu_car_items[3]))
        menu_car_text = "Ваш профиль:\n" + self.get_profile(username)
        if message.chat.username is not None:
            self.drivers['username'][username] = message.chat.username

        # Если заполнены все поля ...
        if username not in self.drivers['about']:
            self.go_about(bot, message)
            return

        if username not in self.drivers['radius']:
            self.go_radius(bot, message)
            return

        if username not in self.drivers['price']:
            self.go_price(bot, message)
            return

            # Инициализируем просмотры
        if username not in self.drivers['views']:
            self.drivers['views'][username] = 0
            # Ставим статус готовности к поиску пассажиров
        self.drivers['status'][username] = 0

        # Сохраним имя пользователя, если есть
        name = ""
        if message.chat.first_name is not None:
            name = name + message.chat.first_name
        if message.chat.last_name is not None:
            name = name + " " + message.chat.last_name
        self.drivers['name'][username] = name

        # Если водитель готов к поиску, то покажем кнопку поиска

        if message.chat.username is not None:
            menu_car.row(types.KeyboardButton(text=self.menu_car_items[6], request_location=True))
            menu_car_text = menu_car_text + f"\n\nНажмите “{self.menu_car_items[6]}”" \
                                            f" (геолокация на телефоне должна быть включена)" \
                                            f" или пришлите свои координаты текстом."
        else:
            menu_car_text = menu_car_text + f"\n\n‼️ Задайте имя пользователя в аккаунте Telegram," \
                                            f" что бы бот мог направить вам пассажиров ‼️"

        bot.send_message(message.chat.id, menu_car_text, reply_markup=menu_car)

    # Функция увеличения счетчика просмотров у водителя
    def inc_impression(self, user_driver):
        current_time = int(time.time())
        # Проверка на смену дат и обнуление
        dt_timestamp = int(datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0)).timestamp())
        if user_driver not in self.drivers['last_impression'] or int(
                self.drivers['last_impression'][user_driver]) < dt_timestamp:
            self.drivers['impressions'][user_driver] = 0
        # Увеличиваем счетчик дня
        self.drivers['impressions'][user_driver] = int(self.drivers['impressions'][user_driver]) + 1
        # Увеличиваем счетчик общий
        self.drivers['views'][user_driver] = int(self.drivers['views'][user_driver]) + 1
        # Запоминаем время последнего показа водительского объявления пользователю
        self.drivers['last_impression'][user_driver] = current_time

    # Формирование списка водителей во время поиска
    def go_search(self, location):
        result_message = ''

        # Перебираем всех водителей
        geo = {}
        for user_driver_ne in self.drivers['status'].keys():
            user_driver = int(user_driver_ne)
            # Нам нужны только активныуе ("в поиске")
            if int(self.drivers['status'][user_driver]) == 1:
                # Вычисляем расстояние до водителя
                dist = get_distance(location['latitude'], location['longitude'],
                                    float(self.drivers['geo_lat'][user_driver]),
                                    float(self.drivers['geo_long'][user_driver])
                                    )
                # Если водитель рядом, то добавляем в результирующий список
                if dist < int(self.drivers['radius'][user_driver]):
                    geo[user_driver] = dist

        # Сортируем и составляем выдачу текстом
        sorted_list = sorted(geo, key=geo.get)
        for user_driver in sorted_list:
            dist = geo[user_driver]
            result_message = result_message + f"🚖 {self.drivers['about'][user_driver].decode('utf-8')}\n" \
                                              f"🚕 {dist:.2f} км\n" \
                                              f"💰 {int(self.drivers['price'][user_driver])} {SYMBOL}/км\n" \
                                              f"💬 @{self.drivers['username'][user_driver].decode('utf-8')}\n\n"
            # Если этого водителя нету в недавнем поиске, то накручиваем ему счетчик просмотра
            self.inc_impression(user_driver)

        s_count = len(sorted_list)
        m_text = "🤷‍ Ничего не найдено! Рядом с Вами нет водителей готовых подвезти вас, придется попробовать позже."
        if s_count > 0:
            m_text = f"Найдено водителей: {s_count}\n\n{result_message}" \
                     f"💬 Можете связаться с любым водителем и договориться с ним о совместной поездке." \
                     " Приятной дороги, не забудьте пристегнуть ремни безопасности!"
        return m_text

    # Получены координаты тем или иным образом от пассажира или водителя
    def go_location(self, bot, message, location):
        username = message.chat.id
        # Определение того кто нажал на кнопку
        if username in self.drivers['status'] and int(self.drivers['status'][username]) >= 0:  # Водитель
            if username in self.drivers['username']:
                # Ставлю водитлею статус "в поиске"
                self.drivers['status'][username] = 1
                self.drivers['geo_long'][username] = location['longitude']
                self.drivers['geo_lat'][username] = location['latitude']
                search_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                search_keyboard.row(types.KeyboardButton(text=self.menu_stop))
                bot.send_message(message.chat.id, f"⏳ Идет поиск. Потенциальным пассажирам в указанном вами радиусе бот"
                                                  f" будет показывать ваше оъявление. Ждите, вам напишут.",
                                 reply_markup=search_keyboard)
        else:  # На кнопку нажал пассажир
            m_text = self.go_search(location)
            bot.send_message(message.chat.id, m_text, reply_markup=self.menu_keyboard)

    def deploy(self):
        bot = telebot.TeleBot(TELE_TOKEN)


        #  try:
        #      bot.polling()
        #  except Exception as e:
        #
        #     print("Error ", e)

        # Стартовое сообщение
        @bot.message_handler(commands=['start'])
        def start_message(message):
            bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            self.go_start(bot, message)

        # Отмена ввода
        @bot.message_handler(commands=['cancel'])
        def cancel_message(message):
            self.go_start(bot, message)

        # Тест вычисления расстояния специальной командой
        @bot.message_handler(commands=['geo'])
        def geo_message(message):
            try:
                lat1 = float(message.text.split(' ')[1])
                long1 = float(message.text.split(' ')[2])
                lat2 = float(message.text.split(' ')[3])
                long2 = float(message.text.split(' ')[4])

                dist = get_distance(lat1, long1, lat2, long2)
                bot.send_message(message.chat.id, f"Расстояние {dist} км")
            except Exception as error:
                bot.send_message(message.chat.id, f"%USERNAME% какбе ошибсо {error}")

        # Вывод админу списка Айди пользователя с именем
        @bot.message_handler(commands=['list'])
        def list_message(message):
            if message.chat.id in ADMIN_LIST:
                me = "Список водителей (ID - имя - просмотры):\n"
                for username in self.drivers['name'].keys():
                    me = me + f"{username.decode('utf-8')} - {self.drivers['name'][username].decode('utf-8')}" \
                              f" - {int(self.drivers['views'][username])}\n"
                bot.send_message(message.chat.id, me)

        # Обработка всех команд
        @bot.message_handler(content_types=['text'])
        def message_text(message):
            username = message.chat.id
            # Обработка текстовых сообщений от водителя, заполняю объявление
            if username in self.drivers['wait'] and int(self.drivers['wait'][username]) == 0:
                if len(message.text) <= ABOUT_LIMIT:
                    self.drivers['about'][username] = message.text
                    self.drivers['wait'][username] = -1
                    self.go_menu_car(bot, message)
                    return
                else:
                    bot.send_message(message.chat.id, f"‼️ Объявление слишком длинное,"
                                                      f" ограничение {ABOUT_LIMIT} символов ‼️")
                    return
            # Обработка текстовых сообщений от водителя, заполняю радиус
            if username in self.drivers['wait'] and int(self.drivers['wait'][username]) == 1:
                if str(message.text).isnumeric():
                    self.drivers['radius'][username] = int(message.text)
                    self.drivers['wait'][username] = -1
                    self.go_menu_car(bot, message)
                    return
                else:
                    bot.send_message(message.chat.id, "‼️ Пожалуйста, ведите число ‼️")
                    return
            # Обработка текстовых сообщений от водителя, заполняю цену за км
            if username in self.drivers['wait'] and int(self.drivers['wait'][username]) == 2:
                if str(message.text).isnumeric():
                    self.drivers['price'][username] = int(message.text)
                    self.drivers['wait'][username] = -1
                    self.go_menu_car(bot, message)
                    return
                else:
                    bot.send_message(message.chat.id, "‼️ Пожалуйста, ведите число ‼️")
                    return

            # Обработка кнопки "Я водитель"
            if message.text == self.menu_items[1]:
                self.go_menu_car(bot, message)
                return
            # Обработка кнопки "Изменить объявление"
            if message.text == self.menu_car_items[0]:
                self.go_about(bot, message)
                return
            # Обработка кнопки "Изменить радиус"
            if message.text == self.menu_car_items[1]:
                self.go_radius(bot, message)
                return
            # Обработка кнопки "Изменить цену"
            if message.text == self.menu_car_items[2]:
                self.go_price(bot, message)
                return
            # Обработка кнопки "Выход"
            if message.text == self.menu_car_items[3]:
                self.drivers['status'][username] = -1
                self.go_start(bot, message)
                return
            # Обработка кнопки "Прекратить поиск"
            if message.text == self.menu_stop and int(self.drivers['status'][username]) == 1:
                self.go_menu_car(bot, message)
                return
            # Обработка отправления координат текстом
            if re.fullmatch("^(-?\d+(\.\d+)?),\s*(-?\d+(\.\d+)?)$", message.text):
                location = {'latitude': float(message.text.split(',')[0]),
                            'longitude': float(message.text.split(',')[1])}
                self.go_location(bot, message, location)
                return
            # Удаление сообщений не подошедших под ожидаемые нажатия кнопок
            bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

        # Реакция на отправление геопозиции
        @bot.message_handler(content_types=['location'])
        def message_geo(message):
            location = {'longitude': message.location.longitude, 'latitude': message.location.latitude}
            self.go_location(bot, message, location)

        # Удаление сообщений  всех типов не подошедших под ожидаемые
        @bot.message_handler(content_types=CONTENT_TYPES)
        def message_any(message):
            bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

        bot.polling()


if __name__ == "__main__":
    taxi = Taxi()
    taxi.deploy()
