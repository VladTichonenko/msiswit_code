from flask import Flask, render_template, request, jsonify, send_file, redirect
import sqlite3
import requests
import os
from urllib.parse import urlencode
import time

app = Flask(__name__)

# Настройки для производительности
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300  # Кэширование статических файлов на 5 минут

# Простой кэш пользователей в памяти (для быстрого доступа)
user_cache = {}
CACHE_TIMEOUT = 300  # 5 минут

# База данных
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    # Создаем таблицу
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language_code TEXT,
            avatar_url TEXT,
            custom_username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем поле custom_username если его нет (для существующих баз данных)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN custom_username TEXT')
        print("Added custom_username column to existing database")
    except sqlite3.OperationalError:
        # Колонка уже существует
        pass
    
    # Создаем индексы для ускорения запросов
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON users(username)')
    
    # Оптимизируем базу данных
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA cache_size=10000')
    cursor.execute('PRAGMA temp_store=MEMORY')
    
    conn.commit()
    conn.close()

def get_user_avatar_url(user_id):
    """Получает URL аватарки пользователя из Telegram"""
    try:
        # Для получения аватарки пользователя из Telegram нужно использовать Bot API
        # Но это требует токен бота и может быть ограничено
        # Пока возвращаем None, в будущем можно реализовать через Telegram Bot API
        return None
    except Exception as e:
        print(f"Ошибка получения аватарки: {e}")
        return None

def save_user_data(user_id, username, first_name, last_name, language_code, avatar_url=None):
    """Сохраняет данные пользователя в базу данных"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    try:
        # Если avatar_url не передан, сохраняем существующую аватарку
        if not avatar_url:
            cursor.execute('SELECT avatar_url FROM users WHERE user_id = ?', (user_id,))
            existing_user = cursor.fetchone()
            if existing_user and existing_user[0]:
                avatar_url = existing_user[0]
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, language_code, avatar_url)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language_code, avatar_url))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения пользователя: {e}")
    finally:
        conn.close()

def get_user_data(user_id):
    """Получает данные пользователя из базы данных"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        if user:
            # Используем custom_username если он есть, иначе username
            display_username = user[7] if user[7] else user[2]  # custom_username или username
            
            return {
                'user_id': user[1],
                'username': display_username,  # Показываем правильный юзернейм
                'original_username': user[2],  # Оригинальный username от бота
                'custom_username': user[7],     # Кастомный юзернейм
                'first_name': user[3],
                'last_name': user[4],
                'language_code': user[5],
                'avatar_url': user[6]
            }
        return None
    except Exception as e:
        print(f"Ошибка получения пользователя: {e}")
        return None
    finally:
        conn.close()

def save_and_get_user_data(user_id, username, first_name, last_name, language_code):
    """Оптимизированная функция: сохраняет и сразу возвращает данные пользователя"""
    # Проверяем кэш
    cache_key = str(user_id)
    current_time = time.time()
    
    if cache_key in user_cache:
        cache_data, cache_time = user_cache[cache_key]
        if current_time - cache_time < CACHE_TIMEOUT:
            # Проверяем, нужно ли обновлять данные
            should_update = (
                cache_data['original_username'] != username or 
                cache_data['first_name'] != first_name or 
                cache_data['last_name'] != last_name or 
                cache_data['language_code'] != language_code
            )
            
            if should_update:
                # Обновляем в БД и кэше
                return _update_user_in_db_and_cache(user_id, username, first_name, last_name, language_code)
            return cache_data
    
    # Если нет в кэше, получаем из БД
    return _update_user_in_db_and_cache(user_id, username, first_name, last_name, language_code)

def _update_user_in_db_and_cache(user_id, username, first_name, last_name, language_code):
    """Обновляет данные пользователя в БД и кэше"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    try:
        # Получаем существующие данные
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        existing_user = cursor.fetchone()
        
        # Сохраняем аватарку и custom_username если они есть
        avatar_url = existing_user[6] if existing_user and existing_user[6] else None
        custom_username = existing_user[7] if existing_user and existing_user[7] else None
        
        # Обновляем/создаем запись - username всегда обновляется от бота
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, language_code, avatar_url, custom_username)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language_code, avatar_url, custom_username))
        
        conn.commit()
        
        # Определяем, какой username показывать
        display_username = custom_username if custom_username else username
        
        # Данные пользователя
        user_data = {
            'user_id': user_id,
            'username': display_username,  # Показываем правильный юзернейм
            'original_username': username,  # Оригинальный от бота
            'custom_username': custom_username,  # Кастомный юзернейм
            'first_name': first_name,
            'last_name': last_name,
            'language_code': language_code,
            'avatar_url': avatar_url
        }
        
        # Сохраняем в кэш
        user_cache[str(user_id)] = (user_data, time.time())
        
        print(f"Updated user {user_id}: display_username={display_username}, original={username}, custom={custom_username}")
        return user_data
    except Exception as e:
        print(f"Ошибка сохранения/получения пользователя: {e}")
        return None
    finally:
        conn.close()

@app.route('/')
def index():
    """Главная страница"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    lang = request.args.get('lang', 'ru')
    
    # Оптимизированное сохранение и получение данных пользователя
    if user_id:
        user_data = save_and_get_user_data(
            user_id=int(user_id),
            username=username,
            first_name=request.args.get('first_name', ''),
            last_name=request.args.get('last_name', ''),
            language_code=lang
        )
    else:
        user_data = None
    
    # Используем username из базы данных, если он есть
    final_username = username
    if user_data and user_data.get('username'):
        final_username = user_data['username']
        print(f"Using username from database for /: {final_username}")
    
    return render_template('index.html', 
                         username=final_username, 
                         user_id=user_id, 
                         lang=lang,
                         user_data=user_data)

@app.route('/user')
def user():
    """Страница пользователя"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    lang = request.args.get('lang', 'ru')
    
    # Получаем данные пользователя из базы
    user_data = None
    final_username = username  # По умолчанию используем переданный username
    
    if user_id:
        try:
            user_id_int = int(user_id)
            user_data = get_user_data(user_id_int)
            
            if user_data and user_data.get('username'):
                # Если в базе есть более свежий юзернейм, используем его
                final_username = user_data['username']
                print(f"Using username from database for /user: {final_username}")
        except (ValueError, TypeError):
            print(f"Invalid user_id: {user_id}")
    
    return render_template('user.html', 
                         username=final_username, 
                         user_id=user_id, 
                         lang=lang,
                         user_data=user_data)

@app.route('/tonconnect_page')
def tonconnect_page():
    """Страница TON Connect"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    first_name = request.args.get('first_name', '')
    last_name = request.args.get('last_name', '')
    lang = request.args.get('lang', 'ru')
    
    # Оптимизированное сохранение и получение данных пользователя
    user_data = None
    avatar_url = None
    
    if user_id:
        user_data = save_and_get_user_data(
            user_id=int(user_id),
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=lang
        )
        if user_data and user_data.get('avatar_url'):
            avatar_url = user_data['avatar_url']
    
    # Используем username из базы данных, если он есть
    final_username = username
    if user_data and user_data.get('username'):
        final_username = user_data['username']
        print(f"Using username from database for /tonconnect_page: {final_username}")
    
    return render_template('tonconect.html', 
                         username=final_username, 
                         user_id=user_id, 
                         first_name=first_name,
                         last_name=last_name,
                         lang=lang,
                         user_data=user_data,
                         avatar_url=avatar_url)

@app.route('/prof')
def prof():
    """Страница профиля"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    first_name = request.args.get('first_name', '')
    last_name = request.args.get('last_name', '')
    lang = request.args.get('lang', 'ru')
    
    # Получаем данные пользователя из базы (включая аватарку)
    user_data = None
    avatar_url = None
    final_username = username  # По умолчанию используем переданный username
    
    if user_id:
        try:
            user_id_int = int(user_id)
            user_data = get_user_data(user_id_int)
            
            if user_data:
                # Если в базе есть более свежий юзернейм, используем его
                if user_data.get('username'):
                    final_username = user_data['username']
                    print(f"Using username from database: {final_username}")
                else:
                    print(f"No username in database, using provided: {username}")
                
                if user_data.get('avatar_url'):
                    avatar_url = user_data['avatar_url']
        except (ValueError, TypeError):
            print(f"Invalid user_id: {user_id}")
    
    return render_template('prof.html', 
                         username=final_username, 
                         user_id=user_id, 
                         first_name=first_name,
                         last_name=last_name,
                         lang=lang,
                         user_data=user_data,
                         avatar_url=avatar_url)

@app.route('/profile')
def profile_alias():
    """Алиас на /prof для совместимости с ссылками вида /profile"""
    qs = request.query_string.decode() if request.query_string else ''
    target = '/prof'
    if qs:
        target = f"{target}?{qs}"
    return redirect(target, code=302)


@app.route('/glav')
def glav():
    """Главная (после TON Connect)"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    first_name = request.args.get('first_name', '')
    last_name = request.args.get('last_name', '')
    lang = request.args.get('lang', 'ru')

    # Загружаем пользователя если есть ID
    user_data = get_user_data(int(user_id)) if user_id else None
    final_username = username
    if user_data and user_data.get('username'):
        final_username = user_data['username']

    return render_template('glav.html',
                           username=final_username,
                           user_id=user_id,
                           first_name=first_name,
                           last_name=last_name,
                           lang=lang,
                           user_data=user_data)


@app.route('/settings')
def settings_page():
    """Страница настроек"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    first_name = request.args.get('first_name', '')
    last_name = request.args.get('last_name', '')
    lang = request.args.get('lang', 'ru')

    user_data = get_user_data(int(user_id)) if user_id else None
    final_username = username
    if user_data and user_data.get('username'):
        final_username = user_data['username']

    return render_template('settings.html',
                           username=final_username,
                           user_id=user_id,
                           first_name=first_name,
                           last_name=last_name,
                           lang=lang,
                           user_data=user_data)


@app.route('/info')
def info_page():
    """Информационная страница"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    first_name = request.args.get('first_name', '')
    last_name = request.args.get('last_name', '')
    lang = request.args.get('lang', 'ru')

    user_data = get_user_data(int(user_id)) if user_id else None
    final_username = username
    if user_data and user_data.get('username'):
        final_username = user_data['username']

    return render_template('info.html',
                           username=final_username,
                           user_id=user_id,
                           first_name=first_name,
                           last_name=last_name,
                           lang=lang,
                           user_data=user_data)
@app.route('/api/user/<int:user_id>/username')
def get_username(user_id):
    """API для получения актуального юзернейма пользователя"""
    try:
        user_data = get_user_data(user_id)
        if user_data and user_data.get('username'):
            return jsonify({'username': user_data['username']})
        else:
            return jsonify({'username': None})
    except Exception as e:
        print(f"Error getting username: {e}")
        return jsonify({'username': None})

@app.route('/api/username', methods=['POST'])
def update_username():
    """API для обновления юзернейма"""
    try:
        data = request.get_json()
        print(f"Received data: {data}")
        user_id = data.get('user_id')
        username = data.get('username')
        
        if not user_id or not username:
            print(f"Missing data: user_id={user_id}, username={username}")
            return jsonify({'ok': False, 'error': 'Missing user_id or username'})
        
        # Обновляем юзернейм в базе данных
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Преобразуем user_id в число
        try:
            user_id = int(user_id)
            print(f"Converted user_id to int: {user_id}")
        except (ValueError, TypeError):
            print(f"Invalid user_id: {user_id}")
            return jsonify({'ok': False, 'error': 'Invalid user_id'})
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        existing_user = cursor.fetchone()
        print(f"Existing user: {existing_user}")
        
        if existing_user:
            # Обновляем существующего пользователя - сохраняем в custom_username
            print(f"Updating user {user_id} with custom username {username}")
            cursor.execute('UPDATE users SET custom_username = ? WHERE user_id = ?', (username, user_id))
        else:
            # Создаем нового пользователя
            print(f"Creating new user {user_id} with custom username {username}")
            cursor.execute('INSERT INTO users (user_id, custom_username) VALUES (?, ?)', (user_id, username))
        
        conn.commit()
        conn.close()
        
        # Обновляем кэш
        if user_id in user_cache:
            user_cache[user_id]['username'] = username
            user_cache[user_id]['username_edited'] = True  # Помечаем, что юзернейм был отредактирован
            print(f"Updated cache for user {user_id}")
        
        print(f"Successfully updated username to: {username}")
        return jsonify({'ok': True, 'username': username})
        
    except Exception as e:
        print(f"Error updating username: {e}")
        return jsonify({'ok': False, 'error': 'Internal server error'})



@app.route('/deepseek')
def deepseek():
    """Страница DeepSeek"""
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    lang = request.args.get('lang', 'ru')
    
    # Получаем данные пользователя из базы (включая аватарку)
    user_data = None
    avatar_url = None
    if user_id:
        user_data = get_user_data(int(user_id))
        if user_data and user_data.get('avatar_url'):
            avatar_url = user_data['avatar_url']
    
    return render_template('deepseek.html', 
                         username=username, 
                         user_id=user_id, 
                         lang=lang,
                         user_data=user_data,
                         avatar_url=avatar_url)

@app.route('/api/user/<int:user_id>/avatar')
def get_user_avatar(user_id):
    """API для получения аватарки пользователя"""
    user_data = get_user_data(user_id)
    if user_data and user_data.get('avatar_url'):
        return jsonify({'avatar_url': user_data['avatar_url']})
    return jsonify({'avatar_url': None})

if __name__ == '__main__':
    init_db()
    # Оптимизированные настройки для продакшена
    app.run(
        host='0.0.0.0', 
        port=8000, 
        debug=False,  # Отключаем debug для производительности
        threaded=True,  # Включаем многопоточность
        use_reloader=False  # Отключаем автоперезагрузку
    )