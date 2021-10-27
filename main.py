import math
import redis
import telebot
from telebot import types
import time
import datetime
import re
import json
import os

# Загружаем секретные ссылки и токены из системы
REDIS_URL = os.environ['REDIS_URL']
TELE_TOKEN = os.environ['TELEGRAM_TOKEN']

# Устанавливаем константы
DEPOSIT_LIMIT = -300  # Минимальный баланс для поиска
ADMIN_LIST = [665812965]  # Список админов для спец команд (тут только Олин)
ABOUT_LIMIT = 100  # Лимит символов в объявлении
SEARCH_LIVE_TIME = 300  # Время жизни поискового запроса
IMPRESSION_COST = 1  # Цена одного показа
CONTENT_TYPES = ["text", "audio", "document", "photo", "sticker", "video", "video_note", "voice", "location", "contact",
                 "new_chat_members", "left_chat_member", "new_chat_title", "new_chat_photo", "delete_chat_photo",
                 "group_chat_created", "supergroup_chat_created", "channel_chat_created", "migrate_to_chat_id",
                 "migrate_from_chat_id", "pinned_message"]


# Главная функция
def app():
    # redis_url = 'redis://:@localhost:6379'  # Для теста на локальном сервере
    redis_url = REDIS_URL
    bot = telebot.TeleBot(TELE_TOKEN)

    # База данных водителей
    drivers = {'about': redis.from_url(redis_url, db=1),
               'radius': redis.from_url(redis_url, db=2),
               'price': redis.from_url(redis_url, db=3),
               'wait': redis.from_url(redis_url, db=4),
               'status': redis.from_url(redis_url, db=5),
               'geo_long': redis.from_url(redis_url, db=6),
               'geo_lat': redis.from_url(redis_url, db=7),
               'impressions': redis.from_url(redis_url, db=8),
               'last_impression': redis.from_url(redis_url, db=9),
               'deposit': redis.from_url(redis_url, db=10),
               'name': redis.from_url(redis_url, db=11),
               'username': redis.from_url(redis_url, db=12)}

    # Реестр поисковых запросов
    clients_search = redis.from_url(redis_url, db=15)

    menu_items = ['👍 Поиск машины', '🚕 Я водитель']
    menu_car_items = ['Изменить объявление', 'Изменить радиус', 'Изменить цену за км', 'Выход', 'Пополнить баланс',
                      'Поддержка',  "✳️ Поиск пассажира ✳️"]
    menu_stop = "⛔️ Прекратить поиск ⛔️"

    # Среднее значение среди водителей по произвольному полю
    def get_avg(field: str):
        tot = 0
        count = 0
        for k in drivers[field].keys():
            tot += int(drivers[field][k])
            count += 1
        if count == 0:
            return 0
        return int(tot / count)

    # Стартовое сообщение
    def go_start(message):
        username = message.chat.id
        menu_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        menu_keyboard.row(types.KeyboardButton(text=menu_items[0], request_location=True),
                          types.KeyboardButton(text=menu_items[1]))
        # Сброс статуса "в поиске пассажира" и ожидания ввода текста
        if username in drivers['status'] and int(drivers['status'][username]) >= 0:
            drivers['status'][username] = -1
        if username in drivers['wait'] and int(drivers['wait'][username]) >= 0:
            drivers['wait'][username] = -1
        # Подсчет статистики водителей (всего и активных), а также пассажиров в поиске
        total = 0
        active = 0
        for dr in drivers['status'].keys():
            total += 1
            if int(drivers['status'][dr]) == 1:
                active += 1
        clients_count = 0
        for _ in clients_search.keys():
            clients_count += 1
        menu_message = f"Водителей зарегестрировно: {total}\nСейчас доступно: {active}\n" \
                       f"Пассажиров в поиске: {clients_count}\nКанал поддержки https://t.me/BelbekTaxi\n" \
                       f"👍 Для поиска машины нажмите “Поиск машины”" \
                       f" (или отправьте свои координаты текстом)," \
                       f" бот предложит связаться с водителями, готовыми приехать за вами. "
        bot.send_message(message.chat.id, menu_message, reply_markup=menu_keyboard, disable_web_page_preview=True)

    # Запрос объявления
    def go_about(message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.id
        # Устанавливаем ожидание текстового ответа для поля "объявление"
        drivers['wait'][username] = 0
        bot.send_message(message.chat.id, f"Расскажите немного о себе и машине (не больше {ABOUT_LIMIT} символов),"
                                          f" например: “Ильдар. Синяя Хонда. Вожу быстро, но аккуратно.”",
                         reply_markup=keyboard)
        return

    # Запрос радиуса поиска
    def go_radius(message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.id
        # Устанавливаем ожидание текстового ответа для радиуса (числового на самом деле, но проверим это позже)
        drivers['wait'][username] = 1
        avg_km = get_avg('radius')
        bot.send_message(message.chat.id, f"Задайте расстояние в километрах на которое вы готовы поехать за пассажиром."
                                          f"\nСреднее среди водителей: {avg_km}", reply_markup=keyboard)
        return

    # Запрос оцены за км
    def go_price(message):
        keyboard = types.ReplyKeyboardRemove()
        username = message.chat.id
        # Устанавливаем ожидание текстового ответа для цены(числового на самом деле, но проверим это позже)
        drivers['wait'][username] = 2
        avg_price = get_avg('price')
        bot.send_message(message.chat.id, f"Напишите сколько денег обычно вы берёте за километр пути (примерно)."
                                          f"\nСреднее среди водителей: {avg_price}", reply_markup=keyboard)
        return

    # Формирование описания профиля водителя
    def get_profile(username):
        info_about = "Поле не заполнено"
        if username in drivers['about']:
            info_about = drivers['about'][username].decode("utf-8")
        info_radius = "Поле не заполнено"
        if username in drivers['radius']:
            info_radius = f"{int(drivers['radius'][username])} км"
        info_price = "Поле не заполнено"
        if username in drivers['price']:
            info_price = f"{int(drivers['price'][username])} руб/км"
        impressions = 0
        if username in drivers['impressions']:
            # Проверка на смену дня и сброс счетчика
            dt_timestamp = int(datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0)).timestamp())
            if int(drivers['last_impression'][username]) < dt_timestamp:
                drivers['impressions'][username] = 0
                current_time = int(time.time())
                drivers['last_impression'][username] = current_time
            impressions = int(drivers['impressions'][username])
        balance = 0
        if username in drivers['deposit']:
            balance = int(drivers['deposit'][username])

        info = f"Объявление: {info_about}\nОриентировочная цена: {info_price}\nРадиус поиска: {info_radius}\n" \
               f"Показов сегодня: {impressions}\nБаланс: {balance}"
        return info

    # Меню водителя
    def go_menu_car(message):
        username = message.chat.id
        menu_car = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        menu_car.row(types.KeyboardButton(text=menu_car_items[0]),
                     types.KeyboardButton(text=menu_car_items[1]))
        menu_car.row(types.KeyboardButton(text=menu_car_items[2]),
                     types.KeyboardButton(text=menu_car_items[3]))
        menu_car_text = "Ваш профиль:\n" + get_profile(username)\
                        + f"\n\nСтоимость одного показа: {IMPRESSION_COST} р." \
                          f"\nМинимальный баланс для поиска: {DEPOSIT_LIMIT} р." \
                          f"\nДля пополнения свяжитесь с @whitejoe (пока так)"
        if message.chat.username is not None:
            drivers['username'][username] = message.chat.username

        # Если заполнены все поля ...
        if username in drivers['about'] and username in drivers['radius'] and username in drivers['price']:
            # Инициализируем баланс
            if username not in drivers['deposit']:
                drivers['deposit'][username] = 0
            # Ставим статус готовности к поиску пассажиров
            drivers['status'][username] = 0

            # Сохраним имя пользователя, если есть
            name = ""
            if message.chat.first_name is not None:
                name = name + message.chat.first_name
            if message.chat.last_name is not None:
                name = name + " " + message.chat.last_name
            drivers['name'][username] = name

        # Если водитель готов к поиску, то покажем кнопку поиска
        if username in drivers['status'] and int(drivers['status'][username]) == 0:
            if message.chat.username is not None:
                if int(drivers['deposit'][username]) >= DEPOSIT_LIMIT:
                    menu_car.row(types.KeyboardButton(text=menu_car_items[6], request_location=True))
                    menu_car_text = menu_car_text + f"\n\n🚕 Для поиска пассажира нажмите “Поиск пассажира” " \
                                                    f"(или отправьте свои координаты текстом)."
                else:   # или ...
                    menu_car_text = menu_car_text + f"\n\nfВаш баланс исчерпан, лимит {DEPOSIT_LIMIT}"
            else:  # покажем ...
                menu_car_text = menu_car_text + f"\n\nЗадайте имя пользователя в аккаунте Telegram," \
                                                f" что бы бот мог направить вам пассажиров."
        else:  # хуй
            menu_car_text = menu_car_text + "\n\n Заполните все поля, что бы начать поиск пассажиров!"
        bot.send_message(message.chat.id, menu_car_text, reply_markup=menu_car)

    # Вычисление расстояния между координатами
    def get_distance(long1, lat1, long2, lat2):

        # Функция вычисления гаверсинуса
        def hav(x):
            return (math.sin(x / 2)) ** 2

        # Радиус текущей планеты (Земля) в км, погрешность 0.5%
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

    # Функция увеличения счетчика просмотров у водителя
    def inc_impression(user_driver):
        current_time = int(time.time())
        # Проверка на смену дат и обнуление
        dt_timestamp = int(datetime.datetime.combine(datetime.date.today(), datetime.time(0, 0, 0)).timestamp())
        if user_driver not in drivers['last_impression'] or int(drivers['last_impression'][user_driver]) < dt_timestamp:
            drivers['impressions'][user_driver] = 0
        # Увеличиваем счетчик
        drivers['impressions'][user_driver] = int(drivers['impressions'][user_driver]) + 1
        # Списываем деньги с баланса
        drivers['deposit'][user_driver] = int(drivers['deposit'][user_driver]) - IMPRESSION_COST
        # Запоминаем время последнего показа водительского объявления пользователю
        drivers['last_impression'][user_driver] = current_time

    # Формирование списка водителей во время поиска
    def go_search(message, location):
        username = message.chat.id
        result_list = []
        search_list = []
        result_message = ''
        # Подгружаем список водителей которых пользователь видел недавно (если они есть)
        if username in clients_search:
            search_list_str = clients_search[username].decode("utf-8")
            search_list = json.loads(search_list_str)
        active_drivers = 0
        # Перебираем всех водителей
        for user_driver_ne in drivers['status'].keys():
            user_driver = user_driver_ne.decode("utf-8")
            # Нам нолько активныуе ("в поиске")
            if int(drivers['status'][user_driver]) == 1:
                active_drivers += 1
                # Вычисляем расстояние до водителя
                dist = get_distance(location['longitude'], location['latitude'],
                                    float(drivers['geo_long'][user_driver]), float(drivers['geo_lat'][user_driver]))
                # Если водитель рядом, то добавляем в результирующий список
                if dist < int(drivers['radius'][user_driver]):
                    result_list.append(user_driver)
                    result_message = result_message + f"🚕 {drivers['about'][user_driver].decode('utf-8')}\n" \
                                                      f"🚖: {dist:.2f} км\n" \
                                                      f"💰: {int(drivers['price'][user_driver])} руб/км\n" \
                                                      f"@{drivers['username'][user_driver].decode('utf-8')}\n\n"
                    # Если этого водителя нету в недавнем поиске, то накручиваем ему счетчик просмотра
                    if user_driver not in search_list:
                        inc_impression(user_driver)
        str_json = json.dumps(result_list)
        # Запоминаем список просмотренных водителей на некоторое время
        clients_search.setex(username, SEARCH_LIVE_TIME, str_json)
        s_count = len(result_list)
        m_text = f"Найдено водителей {s_count} из {active_drivers} активных:\n\n{result_message}"
        if s_count > 0:
            m_text = m_text + "Можете связаться с любым водителем и договориться с ним о совместной поедке." \
                              " Приятной дороги, не забудьте пристегнуть ремни безопасности!"
        bot.send_message(message.chat.id, m_text)

    # Получены координаты тем или иным образом от пассажира или водителя
    def go_location(message, location):
        username = message.chat.id
        # Определение того кто нажал на кнопку
        if username in drivers['status'] and int(drivers['status'][username]) >= 0:  # Водитель
            if int(drivers['deposit'][username]) >= DEPOSIT_LIMIT and username in drivers['username']:
                # Ставлю водитлею статус "в поиске"
                drivers['status'][username] = 1
                drivers['geo_long'][username] = location['longitude']
                drivers['geo_lat'][username] = location['latitude']
                search_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                search_keyboard.row(types.KeyboardButton(text=menu_stop))
                bot.send_message(message.chat.id, f"Идет поиск. Потенциальным пассажирам в указанном вами радиусе бот"
                                                  f" будет показывать ваше оъявление. Ждите, вам напишут.",
                                 reply_markup=search_keyboard)
        else:  # На кнопку нажал пассажир
            go_search(message, location)

    # Старотовое сообщение
    @bot.message_handler(commands=['start'])
    def start_message(message):
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        go_start(message)

    # Тест вычисления расстояния специальной командой
    @bot.message_handler(commands=['geo'])
    def geo_message(message):
        try:
            long1 = float(message.text.split(' ')[1])
            lat1 = float(message.text.split(' ')[2])
            long2 = float(message.text.split(' ')[3])
            lat2 = float(message.text.split(' ')[4])
            dist = get_distance(long1, lat1, long2, lat2)
            bot.send_message(message.chat.id, f"Расстояние {dist} км")
        except Exception as e:
            bot.send_message(message.chat.id,
                             f"%USERNAME% какбе ошибсо {e}")

    # Вывод админу списка Айди пользователя с именем
    @bot.message_handler(commands=['list'])
    def list_message(message):
        if message.chat.id in ADMIN_LIST:
            me = "Список водителей (ID - имя - баланс):\n"
            for username in drivers['name'].keys():
                me = me + f"{username.decode('utf-8')} - {drivers['name'][username].decode('utf-8')}" \
                          f" - {drivers['deposit'][username]}\n"
            bot.send_message(message.chat.id, me)

    # Пополнение депозита админом специальной командой /deposit Айди_пользователя сумма
    @bot.message_handler(commands=['deposit'])
    def deposit_message(message):
        if message.chat.id in ADMIN_LIST:
            try:
                username = message.text.split(' ')[1]
                dep = int(message.text.split(' ')[2])
                new_balance = dep + int(drivers['deposit'][username])
                drivers['deposit'][username] = new_balance
                bot.send_message(message.chat.id,
                                 f"Депозит {drivers['name'][username].decode('utf-8')} пополнен на {dep}, "
                                 f"новый баланс {new_balance}")
            except Exception as e:
                bot.send_message(message.chat.id,
                                 f"Админ, какбе ошибсо {e}")

    # Обработка всех команд
    @bot.message_handler(content_types=['text'])
    def message_text(message):
        username = message.chat.id
        # Обработка текстовых сообщений от водителя, заполняю объявление
        if username in drivers['wait'] and int(drivers['wait'][username]) == 0:
            if len(message.text) <= ABOUT_LIMIT:
                drivers['about'][username] = message.text
                drivers['wait'][username] = -1
                go_menu_car(message)
                return
            else:
                bot.send_message(message.chat.id, f"Объявление слишком длинное, ограничение {ABOUT_LIMIT} символов")
                return
        # Обработка текстовых сообщений от водителя, заполняю радиус
        if username in drivers['wait'] and int(drivers['wait'][username]) == 1:
            if str(message.text).isnumeric():
                drivers['radius'][username] = int(message.text)
                drivers['wait'][username] = -1
                go_menu_car(message)
                return
            else:
                bot.send_message(message.chat.id, "Пожалуйста, ведите число")
                return
        # Обработка текстовых сообщений от водителя, заполняю цену за км
        if username in drivers['wait'] and int(drivers['wait'][username]) == 2:
            if str(message.text).isnumeric():
                drivers['price'][username] = int(message.text)
                drivers['wait'][username] = -1
                go_menu_car(message)
                return
            else:
                bot.send_message(message.chat.id, "Пожалуйста, ведите число")
                return

        # Обработка кнопки "Я водитель"
        if message.text == menu_items[1]:
            go_menu_car(message)
            return
        # Обработка кнопки "Изменить объявление"
        if message.text == menu_car_items[0]:
            go_about(message)
            return
        # Обработка кнопки "Изменить радиус"
        if message.text == menu_car_items[1]:
            go_radius(message)
            return
        # Обработка кнопки "Изменить цену"
        if message.text == menu_car_items[2]:
            go_price(message)
            return
        # Обработка кнопки "Выход"
        if message.text == menu_car_items[3]:
            drivers['status'][username] = -1
            go_start(message)
            return
        # Обработка кнопки "Прекратить поиск"
        if message.text == menu_stop and int(drivers['status'][username]) == 1:
            go_menu_car(message)
            return
        # Обработка отправления координат текстом
        if re.fullmatch("^(-?\d+(\.\d+)?),\s*(-?\d+(\.\d+)?)$", message.text):
            location = {'longitude': float(message.text.split(',')[0]), 'latitude': float(message.text.split(',')[1])}
            go_location(message, location)
            return
        # Удаление сообщений не подошедших под ожидаемые нажатия кнопок
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    # Реакция на отправление геопозиции
    @bot.message_handler(content_types=['location'])
    def message_geo(message):
        location = {'longitude': message.location.longitude, 'latitude': message.location.latitude}
        go_location(message, location)

    # Удаление сообщений  всех типов не подошедших под ожидаемые
    @bot.message_handler(content_types=CONTENT_TYPES)
    def message_any(message):
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    bot.polling()


if __name__ == "__main__":
    app()
