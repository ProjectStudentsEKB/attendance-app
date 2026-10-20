from supabase import create_client
import time  # добавь в самый верх файла, если его нет

# ТВОИ ДАННЫЕ (URL уже правильный, ключ вставь свой)
SUPABASE_URL = "https://qmtblohchywocxempwhi.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFtdGJsb2hjaHl3b2N4ZW1wd2hpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTIxMjQ2NzUsImV4cCI6MjEwNzcwMDY3NX0.uHThi1J4DKW3rVyjGF6zK6xzaERDXQABdyxFFVk9TX8" 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============== АВТОРИЗАЦИЯ ==============

def sign_up(email, password, full_name, role, group_id=None):
    """Регистрация в Supabase Auth. Профиль создается автоматически через триггер."""
    try:
        auth_res = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name,
                    "role": role,
                    "group_id": group_id
                }
            }
        })
        # Возвращаем True и ID созданного пользователя
        return True, auth_res.user.id 
    except Exception as e:
        return False, str(e)

def sign_in(email, password):
    """Вход в систему"""
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        return True, res.user
    except Exception as e:
        return False, str(e)

def sign_out():
    supabase.auth.sign_out()

def get_profile():
    """Получает профиль текущего вошедшего пользователя"""
    try:
        user = supabase.auth.get_user()
        if not user or not user.user:
            return None
        # Берем данные из таблицы users
        res = supabase.table("users").select("*").eq("id", user.user.id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

# ============== ГРУППЫ ==============

def get_groups():
    res = supabase.table("groups").select("*").order("name").execute()
    return res.data

def add_group(name):
    try:
        supabase.table("groups").insert({"name": name}).execute()
        return True
    except Exception:
        return False

# ============== СТУДЕНТЫ ==============

def get_students(group_id):
    """Получает список студентов (роль student), привязанных к группе"""
    res = supabase.table("users").select("id, full_name").eq("group_id", group_id).eq("role", "student").execute()
    return res.data

# ============== ЗАНЯТИЯ ==============

def start_lesson(group_id, teacher_id, lat=None, lon=None):
    """Создает новое занятие и возвращает его ID"""
    res = supabase.table("lessons").insert({
        "group_id": group_id,
        "teacher_id": teacher_id,
        "is_active": True,
        "latitude": lat,
        "longitude": lon
    }).execute()
    return res.data[0]["id"] if res.data else None

def get_lesson_coords(lesson_id):
    """Получает координаты занятия"""
    res = supabase.table("lessons").select("latitude, longitude").eq("id", lesson_id).execute()
    if res.data:
        return res.data[0]["latitude"], res.data[0]["longitude"]
    return None, None

def finish_lesson(lesson_id):
    supabase.table("lessons").update({"is_active": False}).eq("id", lesson_id).execute()

def get_attendance(lesson_id):
    """Возвращает список ID студентов, которые отметились"""
    res = supabase.table("attendance").select("student_id").eq("lesson_id", lesson_id).execute()
    return [row["student_id"] for row in res.data]

def mark_all_present(lesson_id, student_ids):
    """Для теста: отмечает всех студентов группы"""
    data = [{"lesson_id": lesson_id, "student_id": sid} for sid in student_ids]
    if data:
        supabase.table("attendance").insert(data).execute()

# ============== СТАТИСТИКА ==============

def get_student_attendance(student_id):
    """Возвращает список посещений для студента"""
    res = supabase.table("attendance").select(
        "status, marked_at, lessons(created_at, group_id)"
    ).eq("student_id", student_id).execute()
    return res.data

def mark_student_present(lesson_id, student_id, qr_timestamp):
    """Отмечает студента, проверяя, что QR-код свежий (не старше 20 секунд)"""
    try:
        # Проверка времени!
        current_time = int(time.time())
        if current_time - int(qr_timestamp) > 20:
            return False, "QR-код устарел. Попроси преподавателя обновить экран."

        # Проверяем, не отмечен ли он уже
        existing = supabase.table("attendance").select("id").eq("lesson_id", lesson_id).eq("student_id", student_id).execute()
        if existing.data:
            return True, "Ты уже отмечен на этом занятии!"
            
        supabase.table("attendance").insert({
            "lesson_id": lesson_id,
            "student_id": student_id,
            "status": "present"
        }).execute()
        return True, "Успешно отмечен!"
    except Exception as e:
        return False, str(e)

def get_user_device_id(user_id):
    """Получает ID устройства, привязанного к пользователю"""
    res = supabase.table("users").select("device_id").eq("id", user_id).execute()
    if res.data:
        return res.data[0].get("device_id")
    return None

def bind_device(user_id, device_id):
    """Привязывает текущее устройство к аккаунту"""
    supabase.table("users").update({"device_id": device_id}).eq("id", user_id).execute()

# ============== РЕЕСТР И РЕГИСТРАЦИЯ ==============

def get_registry_groups():
    """Получает список групп, в которых есть НЕзарегистрированные студенты. Сортирует по алфавиту."""
    res = supabase.table("students_registry")\
        .select("group_name")\
        .eq("is_active", True)\
        .eq("is_registered", False)\
        .execute()
    # Убираем дубликаты и сортируем
    groups = sorted(list(set([row["group_name"] for row in res.data])))
    return groups

def get_registry_students(group_name):
    """Получает список доступных студентов для группы, сортирует по ФИО."""
    res = supabase.table("students_registry")\
        .select("id, full_name")\
        .eq("group_name", group_name)\
        .eq("is_registered", False)\
        .eq("is_active", True)\
        .order("full_name")\
        .execute()
    return res.data

def verify_and_bind_student(registry_id, entered_code, new_user_id):
    """Проверяет код и привязывает созданный аккаунт к реестру"""
    # 1. Ищем студента по ID
    res = supabase.table("students_registry").select("*").eq("id", registry_id).execute()
    if not res.data:
        return False, "Студент не найден в реестре"
    
    student = res.data[0]
    
    # 2. Проверяем код
    if student["registration_code"] != entered_code:
        return False, "Неверный персональный код!"
    
    # 3. Проверяем, не зарегистрирован ли он уже
    if student["is_registered"]:
        return False, "Этот студент уже зарегистрирован в системе!"

    # 4. Все ок - обновляем запись
    try:
        supabase.table("students_registry").update({
            "is_registered": True,
            "registered_user_id": new_user_id
        }).eq("id", registry_id).execute()
        return True, "Успешно"
    except Exception as e:
        return False, str(e)

def get_group_id_by_name(group_name):
    """Ищет ID группы в таблице groups."""
    res = supabase.table("groups").select("id").eq("name", group_name).execute()
    if res.data:
        return res.data[0]["id"]
    return None

# ============== АДМИНИСТРАТОР ==============

def get_all_students_for_admin(search_query=""):
    """Получает список всех студентов для панели админа (с поиском)"""
    query = supabase.table("users").select(
        "id, full_name, email, device_id, device_reset_count, groups(name)"
    ).eq("role", "student")
    
    if search_query:
        query = query.ilike("full_name", f"%{search_query}%")
        
    res = query.order("full_name").execute()
    return res.data

def reset_student_device(student_id):
    """Сбрасывает device_id и увеличивает счетчик"""
    try:
        # 1. Получаем текущий счетчик
        user = supabase.table("users").select("device_reset_count").eq("id", student_id).execute()
        current_count = user.data[0]["device_reset_count"] if user.data else 0
        
        # 2. Обнуляем device_id и увеличиваем счетчик
        supabase.table("users").update({
            "device_id": None,
            "device_reset_count": current_count + 1
        }).eq("id", student_id).execute()
        return True
    except Exception as e:
        print(f"Ошибка сброса: {e}")
        return False

def get_group_stats(group_id):
    """Собирает статистику посещаемости для группы"""
    # 1. Получаем всех студентов группы
    students = supabase.table("users").select("id, full_name")\
        .eq("group_id", group_id).eq("role", "student").order("full_name").execute()
    
    # 2. Получаем все занятия этой группы
    lessons = supabase.table("lessons").select("id").eq("group_id", group_id).execute()
    lesson_ids = [l["id"] for l in lessons.data]
    total_lessons = len(lesson_ids)
    
    if total_lessons == 0:
        return [], 0  # Если занятий не было

    # 3. Получаем все отметки посещаемости для этих занятий
    attendance = supabase.table("attendance").select("student_id, lesson_id")\
        .in_("lesson_id", lesson_ids).execute()
    
    result = []
    for s in students.data:
        # Считаем, сколько раз этот студент был отмечен
        present_count = sum(1 for a in attendance.data if a["student_id"] == s["id"])
        percent = round((present_count / total_lessons * 100), 1)
        
        result.append({
            "full_name": s["full_name"],
            "present": present_count,
            "total": total_lessons,
            "percent": percent
        })
    
    return result, total_lessons