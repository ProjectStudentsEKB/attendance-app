import flet as ft
import supabase_db as db
import qr_utils
import asyncio
import uuid
import time as _time
from datetime import datetime
import math
import flet_geolocator as fg
import flet_camera as fc
from pyzbar.pyzbar import decode
from PIL import Image
import io

async def main(page: ft.Page):
    page.title = "Учёт посещаемости"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0

    prefs = ft.SharedPreferences()
    device_id = await prefs.get("my_device_id")
    if not device_id:
        device_id = str(uuid.uuid4())
        await prefs.set("my_device_id", device_id)

    state = {"user": None, "view": "login", "reg_role": "student", "reg_email": "", "reg_password": ""}
    root = ft.Container(expand=True)

    # ==========================================================
    # ЭКРАН ВХОДА
    # ==========================================================
    def build_login():
        email_field = ft.TextField(label="Email", width=320)
        password_field = ft.TextField(label="Пароль", password=True, can_reveal_password=True, width=320)
        error_text = ft.Text("", color=ft.Colors.RED)
        
        login_btn = ft.Button("Войти", width=320)
        loading_ring = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        
        async def on_login(e):
            error_text.value = ""
            if not email_field.value or not password_field.value:
                error_text.value = "Заполни все поля"
                page.update()
                return
            
            login_btn.content = ft.Row([
                ft.Text("Подождите, идет вход...", color=ft.Colors.WHITE),
                loading_ring
            ], alignment=ft.MainAxisAlignment.CENTER)
            login_btn.disabled = True
            loading_ring.visible = True
            page.update()
            
            try:
                success, msg = await asyncio.to_thread(db.sign_in, email_field.value, password_field.value)
                if success:
                    profile = await asyncio.to_thread(db.get_profile)
                    saved_device = await asyncio.to_thread(db.get_user_device_id, profile["id"])
                    
                    if saved_device is None:
                        await asyncio.to_thread(db.bind_device, profile["id"], device_id)
                        state["user"] = profile
                        render()
                    elif saved_device == device_id:
                        state["user"] = profile
                        render()
                    else:
                        await asyncio.to_thread(db.sign_out)
                        error_text.value = "❌ Вход заблокирован: аккаунт привязан к другому устройству!"
                        login_btn.content = "Войти"
                        login_btn.disabled = False
                        loading_ring.visible = False
                        page.update()
                else:
                    error_text.value = "Неверный email или пароль"
                    login_btn.content = "Войти"
                    login_btn.disabled = False
                    loading_ring.visible = False
                    page.update()
            except Exception as ex:
                error_text.value = f"Ошибка сети: Проверьте интернет"
                login_btn.content = "Войти"
                login_btn.disabled = False
                loading_ring.visible = False
                page.update()

        login_btn.on_click = on_login

        async def goto_register(e):
            state["view"] = "register"
            state["reg_role"] = "student"
            render()

        return ft.Container(
            content=ft.Column([
                ft.Text("Вход", size=32, weight=ft.FontWeight.BOLD),
                email_field, password_field, error_text,
                login_btn,
                ft.TextButton("Ещё нет аккаунта? Зарегистрироваться", on_click=goto_register),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            alignment=ft.Alignment.CENTER, expand=True, padding=30,
        )

    # ==========================================================
    # ЭКРАН РЕГИСТРАЦИИ
    # ==========================================================
    def build_register():
        current_role = state["reg_role"]
        
        email_field = ft.TextField(label="Email", width=400, value=state["reg_email"])
        password_field = ft.TextField(label="Пароль (мин. 6 символов)", password=True, can_reveal_password=True, width=400, value=state["reg_password"])
        
        def on_role_change(e):
            state["reg_role"] = e.control.value
            state["reg_email"] = email_field.value
            state["reg_password"] = password_field.value
            render() 

        role_dropdown = ft.Dropdown(
            label="Кто вы?", width=400, value=current_role,
            options=[
                ft.DropdownOption(key="student", text="Студент"),
                ft.DropdownOption(key="teacher", text="Преподаватель"),
            ],
            on_select=on_role_change
        )

        error_text = ft.Text("", color=ft.Colors.RED)
        
        register_btn = ft.Button("Зарегистрироваться", width=400)
        loading_ring = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

        if current_role == "student":
            group_dd = ft.Dropdown(label="Выберите группу", width=400)
            student_dd = ft.Dropdown(label="Выберите свое ФИО", width=400)
            code_field = ft.TextField(label="Персональный код (из деканата)", width=400)
            
            # Безопасная загрузка групп
            try:
                groups = db.get_registry_groups()
                for g in groups:
                    group_dd.options.append(ft.DropdownOption(key=g, text=g))
            except:
                pass

            async def on_group_change(e):
                student_dd.options.clear()
                student_dd.value = None
                code_field.value = ""
                if group_dd.value:
                    try:
                        students = await asyncio.to_thread(db.get_registry_students, group_dd.value)
                        if not students:
                            student_dd.options.append(ft.DropdownOption(key="none", text="Нет свободных студентов"))
                        else:
                            for s in students:
                                student_dd.options.append(ft.DropdownOption(key=s["id"], text=s["full_name"]))
                    except:
                        student_dd.options.append(ft.DropdownOption(key="err", text="Ошибка сети"))
                page.update()
            group_dd.on_select = on_group_change

            async def on_register(e):
                error_text.value = ""
                email = (email_field.value or "").strip()
                password = password_field.value or ""

                if not email or not password:
                    error_text.value = "Заполни Email и пароль"
                    page.update()
                    return
                
                if not group_dd.value or not student_dd.value or not code_field.value or student_dd.value == "none":
                    error_text.value = "Выбери группу, ФИО и введи код"
                    page.update()
                    return
                
                register_btn.content = ft.Row([ft.Text("Подождите...", color=ft.Colors.WHITE), loading_ring], alignment=ft.MainAxisAlignment.CENTER)
                register_btn.disabled = True
                loading_ring.visible = True
                page.update()
                
                try:
                    success, result = await asyncio.to_thread(db.sign_up, email, password, "", "student", None)
                    if not success:
                        error_text.value = "Эта почта уже зарегистрирована." if "User already registered" in str(result) else f"Ошибка: {result}"
                        register_btn.content = "Зарегистрироваться"
                        register_btn.disabled = False
                        loading_ring.visible = False
                        page.update()
                        return
                    
                    new_user_id = result 
                    ok, msg = await asyncio.to_thread(db.verify_and_bind_student, student_dd.value, code_field.value.upper(), new_user_id)
                    if not ok:
                        error_text.value = msg
                        register_btn.content = "Зарегистрироваться"
                        register_btn.disabled = False
                        loading_ring.visible = False
                        page.update()
                        return
                    
                    reg_data = await asyncio.to_thread(db.supabase.table("students_registry").select("full_name").eq("id", student_dd.value).execute)
                    real_name = reg_data.data[0]["full_name"]
                    grp_id = await asyncio.to_thread(db.get_group_id_by_name, group_dd.value)
                    
                    await asyncio.to_thread(db.supabase.table("users").update({
                        "full_name": real_name,
                        "group_id": grp_id
                    }).eq("id", new_user_id).execute)

                    await asyncio.to_thread(db.sign_in, email, password)
                    state["user"] = await asyncio.to_thread(db.get_profile)
                    state["reg_role"] = "student"
                    render()
                except Exception as ex:
                    error_text.value = "Ошибка сети при регистрации"
                    register_btn.content = "Зарегистрироваться"
                    register_btn.disabled = False
                    loading_ring.visible = False
                    page.update()

            form_fields = [group_dd, student_dd, code_field]
            register_btn.on_click = on_register

        else:
            full_name_field = ft.TextField(label="ФИО Преподавателя", width=400)
            teacher_code_field = ft.TextField(label="Секретный код преподавателя", password=True, can_reveal_password=True, width=400)

            async def on_register(e):
                error_text.value = ""
                email = (email_field.value or "").strip()
                password = password_field.value or ""
                f_name = (full_name_field.value or "").strip()
                t_code = (teacher_code_field.value or "").strip()

                if not email or not password or not f_name:
                    error_text.value = "Заполни Email, пароль и ФИО"
                    page.update()
                    return
                
                register_btn.content = ft.Row([ft.Text("Подождите...", color=ft.Colors.WHITE), loading_ring], alignment=ft.MainAxisAlignment.CENTER)
                register_btn.disabled = True
                loading_ring.visible = True
                page.update()

                try:
                    real_teacher_code = await asyncio.to_thread(db.get_setting, "teacher_code")
                    if t_code != real_teacher_code:
                        error_text.value = "Неверный секретный код преподавателя!"
                        page.update()
                        register_btn.content = "Зарегистрироваться"
                        register_btn.disabled = False
                        loading_ring.visible = False
                        return

                    success, result = await asyncio.to_thread(db.sign_up, email, password, f_name, "teacher", None)
                    if success:
                        await asyncio.to_thread(db.sign_in, email, password)
                        state["user"] = await asyncio.to_thread(db.get_profile)
                        state["reg_role"] = "student"
                        render()
                    else:
                        error_text.value = "Эта почта уже зарегистрирована." if "User already registered" in str(result) else f"Ошибка: {result}"
                        register_btn.content = "Зарегистрироваться"
                        register_btn.disabled = False
                        loading_ring.visible = False
                        page.update()
                except Exception:
                    error_text.value = "Ошибка сети"
                    register_btn.content = "Зарегистрироваться"
                    register_btn.disabled = False
                    loading_ring.visible = False
                    page.update()

            form_fields = [full_name_field, teacher_code_field]
            register_btn.on_click = on_register

        async def goto_login(e):
            state["view"] = "login"
            render()

        return ft.Container(
            content=ft.Column([
                ft.Text("Регистрация", size=32, weight=ft.FontWeight.BOLD),
                email_field, 
                password_field, 
                role_dropdown, 
                *form_fields, 
                error_text,
                register_btn,
                ft.TextButton("Уже есть аккаунт? Войти", on_click=goto_login),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            alignment=ft.Alignment.CENTER, expand=True, padding=30,
        )

    # ==========================================================
    # ПРИЛОЖЕНИЕ ПРЕПОДАВАТЕЛЯ
    # ==========================================================
    def build_teacher_app():
        user = state["user"]
        current_group_id = {"value": None}

        home_screen = ft.Column([
            ft.Text(f"🏠 Здравствуйте, {user['full_name']}!", size=26, weight=ft.FontWeight.BOLD),
            ft.Text("Выберите раздел в меню слева."),
        ], spacing=20)

        group_name_field = ft.TextField(label="Название группы", hint_text="ИС-21", width=300)
        groups_list = ft.Column(spacing=10)

        # Делаем асинхронным!
        async def refresh_groups():
            groups_list.controls.clear()
            try:
                groups = await asyncio.to_thread(db.get_groups)
                if not groups:
                    groups_list.controls.append(ft.Text("Нет групп. Добавь первую!", italic=True, color=ft.Colors.GREY))
                else:
                    for g in groups:
                        students = await asyncio.to_thread(db.get_students, g["id"])
                        groups_list.controls.append(ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.PEOPLE),
                                ft.Text(g["name"], size=18, weight=ft.FontWeight.BOLD),
                                ft.Text(f"{len(students)} студ.", color=ft.Colors.GREY, size=13),
                                ft.Icon(ft.Icons.CHEVRON_RIGHT),
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            padding=15, bgcolor=ft.Colors.BLUE_50, border_radius=8,
                            on_click=lambda e, gid=g["id"], n=g["name"]: open_group(gid, n),
                            ink=True))
            except:
                groups_list.controls.append(ft.Text("Ошибка загрузки групп (проверьте сеть)", color=ft.Colors.RED))
            page.update()

        async def on_add_group(e):
            name = (group_name_field.value or "").strip()
            if not name:
                group_name_field.error_text = "Введи название"
                page.update()
                return
            try:
                if await asyncio.to_thread(db.add_group, name):
                    group_name_field.value = ""
                    group_name_field.error_text = None
                    await refresh_groups()
                else:
                    group_name_field.error_text = "Такая группа уже есть"
            except:
                group_name_field.error_text = "Ошибка сети"
            page.update()

        groups_screen = ft.Column([
            ft.Text("👥 Группы", size=28, weight=ft.FontWeight.BOLD),
            ft.Row([group_name_field, ft.Button("Добавить", icon=ft.Icons.ADD, on_click=on_add_group)], spacing=10),
            ft.Divider(),
            groups_list,
        ], spacing=20, scroll=ft.ScrollMode.AUTO)

        students_title = ft.Text("", size=28, weight=ft.FontWeight.BOLD)
        students_list = ft.Column(spacing=10)

        async def refresh_students():
            students_list.controls.clear()
            gid = current_group_id["value"]
            if gid is None:
                page.update()
                return
            try:
                students = await asyncio.to_thread(db.get_students, gid)
                if not students:
                    students_list.controls.append(ft.Text("Нет зарегистрированных студентов.", italic=True, color=ft.Colors.GREY))
                else:
                    for s in students:
                        students_list.controls.append(ft.Container(
                            content=ft.Row([ft.Icon(ft.Icons.PERSON), ft.Text(s["full_name"], size=16)]),
                            padding=10, bgcolor=ft.Colors.GREEN_50, border_radius=8))
            except:
                students_list.controls.append(ft.Text("Ошибка загрузки", color=ft.Colors.RED))
            page.update()

        students_screen = ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: page.run_task(switch_screen, 1)), students_title]),
            ft.Text("Студенты, которые зарегистрировались в этой группе:", color=ft.Colors.GREY),
            ft.Divider(),
            students_list,
        ], spacing=20, scroll=ft.ScrollMode.AUTO)

        lesson_group_dd = ft.Dropdown(label="Группа", width=320, options=[])
        lesson_status = ft.Text("", weight=ft.FontWeight.BOLD)
        
        qr_lesson_id = {"value": None}
        qr_lesson_info = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        BLANK_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        qr_image = ft.Image(src=BLANK_IMG, width=320, height=320, fit=ft.BoxFit.CONTAIN)
        qr_countdown = ft.Text("", size=14, color=ft.Colors.GREY)
        qr_attendees_count = ft.Text("", size=15, weight=ft.FontWeight.BOLD)
        qr_attendees_list = ft.Column(spacing=5)
        qr_auto_thread = {"running": False}

        async def refresh_lesson_groups():
            lesson_group_dd.options.clear()
            try:
                groups = await asyncio.to_thread(db.get_groups)
                for g in groups:
                    lesson_group_dd.options.append(ft.DropdownOption(key=g["id"], text=g["name"]))
            except:
                pass
            page.update()

        def refresh_qr():
            if qr_lesson_id["value"] is None: return
            token = qr_utils.make_lesson_token(qr_lesson_id["value"])
            b64 = qr_utils.make_qr_base64(token)
            qr_image.src = f"data:image/png;base64,{b64}"
            qr_countdown.value = f"⏱ Обновится через {qr_utils.seconds_remaining()} сек"
            page.update()

        async def refresh_attendees():
            qr_attendees_list.controls.clear()
            if qr_lesson_id["value"] is None or not lesson_group_dd.value:
                page.update()
                return
            try:
                all_students = await asyncio.to_thread(db.get_students, lesson_group_dd.value)
                present_ids = await asyncio.to_thread(db.get_attendance, qr_lesson_id["value"])
                
                qr_attendees_count.value = f"✅ Отметались: {len(present_ids)} из {len(all_students)}"

                if not present_ids:
                    qr_attendees_list.controls.append(ft.Text("Пока никто не отметился.", italic=True, color=ft.Colors.GREY, size=12))
                else:
                    for sid in present_ids:
                        name = next((s["full_name"] for s in all_students if s["id"] == sid), "—")
                        qr_attendees_list.controls.append(ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=16),
                            ft.Text(name, size=13),
                        ], spacing=5))
            except:
                qr_attendees_count.value = "Ошибка обновления"
            page.update()

        async def qr_loop():
            while qr_auto_thread["running"]:
                await asyncio.sleep(10)
                if qr_lesson_id["value"] is None: break
                try:
                    refresh_qr()
                    await refresh_attendees()
                except Exception as ex:
                    print(f"err: {ex}"); break
            qr_auto_thread["running"] = False

        def start_qr_auto_refresh():
            if qr_auto_thread["running"]: return
            qr_auto_thread["running"] = True
            page.run_task(qr_loop)

        def stop_qr_auto_refresh():
            qr_auto_thread["running"] = False

        async def on_start_lesson(e):
            lesson_status.value = ""
            if not lesson_group_dd.value:
                lesson_status.value = "Выбери группу"
                lesson_status.color = ft.Colors.RED
                page.update()
                return
            
            lesson_status.value = "Запрос GPS..."
            lesson_status.color = ft.Colors.BLUE
            page.update()

            geo = fg.Geolocator()
            try:
                pos = await geo.get_current_position_async()
                lat = pos.latitude if pos else None
                lon = pos.longitude if pos else None
            except Exception:
                lat, lon = None, None
            
            try:
                gid = lesson_group_dd.value
                lid = await asyncio.to_thread(db.start_lesson, gid, user["id"], lat, lon)
                now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                
                qr_lesson_id["value"] = lid
                gname = next((g["name"] for g in lesson_group_dd.options if g.key == gid), "Группа")
                qr_lesson_info.value = f"Группа: {gname} | Начато: {now_str}"
                
                await switch_screen(5)
                refresh_qr()
                await refresh_attendees()
                start_qr_auto_refresh()
            except:
                lesson_status.value = "Ошибка сети"
                lesson_status.color = ft.Colors.RED
                page.update()

        async def on_mark_all(e):
            if qr_lesson_id["value"] is None or not lesson_group_dd.value: return
            try:
                students = await asyncio.to_thread(db.get_students, lesson_group_dd.value)
                if not students:
                    qr_countdown.value = "⚠️ В этой группе нет зарегистрированных студентов!"
                    qr_countdown.color = ft.Colors.RED
                    page.update()
                    return
                await asyncio.to_thread(db.mark_all_present, qr_lesson_id["value"], [s["id"] for s in students])
                await refresh_attendees()
            except:
                pass

        async def on_finish_lesson(e):
            stop_qr_auto_refresh()
            if qr_lesson_id["value"]:
                try:
                    await asyncio.to_thread(db.finish_lesson, qr_lesson_id["value"])
                except:
                    pass
            qr_lesson_id["value"] = None
            await switch_screen(3)

        lesson_screen = ft.Column([
            ft.Text("📅 Занятие", size=28, weight=ft.FontWeight.BOLD),
            ft.Text("Выбери группу. Дата и время проставятся автоматически.", color=ft.Colors.GREY),
            ft.Divider(), ft.Row([lesson_group_dd]), ft.Container(height=10),
            ft.Button("▶  Начать занятие", icon=ft.Icons.PLAY_ARROW, on_click=on_start_lesson,
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, padding=20), width=320),
            lesson_status,
        ], spacing=15, scroll=ft.ScrollMode.AUTO)

        qr_screen = ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: (stop_qr_auto_refresh(), page.run_task(switch_screen, 3))),
                    ft.Text("📱 QR-код занятия", size=26, weight=ft.FontWeight.BOLD)]),
            qr_lesson_info, ft.Divider(),
            ft.Container(content=qr_image, alignment=ft.Alignment.CENTER, padding=10),
            ft.Row([qr_countdown, ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: (refresh_qr(), page.run_task(refresh_attendees)))], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(), qr_attendees_count, qr_attendees_list, ft.Container(height=10),
            ft.Row([
                ft.Button("✅ Отметить всех вручную", on_click=on_mark_all),
                ft.Button("⏹ Завершить", icon=ft.Icons.STOP, on_click=on_finish_lesson,
                                  style=ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE)),
            ], spacing=10),
        ], spacing=12, scroll=ft.ScrollMode.AUTO)

        stats_group_dd = ft.Dropdown(label="Выберите группу", width=300, options=[])
        stats_summary = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        stats_list = ft.Column(spacing=8)

        async def refresh_stats_groups():
            stats_group_dd.options.clear()
            try:
                groups = await asyncio.to_thread(db.get_groups)
                for g in groups:
                    stats_group_dd.options.append(ft.DropdownOption(key=g["id"], text=g["name"]))
            except:
                pass
            page.update()

        def color_for(p):
            if p >= 80: return ft.Colors.GREEN, ft.Colors.GREEN_50
            elif p >= 60: return ft.Colors.ORANGE, ft.Colors.ORANGE_50
            return ft.Colors.RED, ft.Colors.RED_50

        async def refresh_stats(e=None):
            stats_list.controls.clear()
            stats_summary.value = ""
            if not stats_group_dd.value:
                page.update()
                return
            try:
                stats, total_lessons = await asyncio.to_thread(db.get_group_stats, stats_group_dd.value)
                
                if total_lessons == 0:
                    stats_summary.value = "⚠️ У группы ещё нет проведённых занятий"
                    stats_summary.color = ft.Colors.ORANGE
                    page.update()
                    return
                    
                if not stats:
                    stats_summary.value = "В группе нет зарегистрированных студентов."
                    page.update()
                    return

                total_present_all = sum(s["present"] for s in stats)
                total_possible = total_lessons * len(stats)
                group_percent = round(total_present_all / total_possible * 100, 1) if total_possible else 0

                stats_summary.value = f"📊 По группе: {group_percent}% ({len(stats)} студ., {total_lessons} занятий)"
                stats_summary.color = ft.Colors.BLUE_700

                for s in stats:
                    p = s["percent"]
                    color, bg = color_for(p)
                    stats_list.controls.append(ft.Container(
                        content=ft.Row([
                            ft.Text(s["full_name"], expand=True, size=15),
                            ft.Text(f"{s['present']} / {s['total']}", size=13, color=ft.Colors.GREY),
                            ft.Container(content=ft.Text(f"{p}%", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                                         bgcolor=color, padding=10, border_radius=20),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        padding=10, bgcolor=bg, border_radius=8))
            except:
                stats_summary.value = "Ошибка загрузки статистики"
                stats_summary.color = ft.Colors.RED
            page.update()

        stats_group_dd.on_select = lambda e: page.run_task(refresh_stats)

        stats_screen = ft.Column([
            ft.Text("📊 Статистика", size=28, weight=ft.FontWeight.BOLD),
            ft.Row([stats_group_dd, ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: page.run_task(refresh_stats))], spacing=10),
            stats_summary,
            ft.Divider(),
            stats_list,
        ], spacing=15, scroll=ft.ScrollMode.AUTO)

        screens = [home_screen, groups_screen, students_screen, lesson_screen, stats_screen, qr_screen]
        content_area = ft.Container(content=screens[0], padding=20, expand=True)

        # Делаем switch_screen асинхронным!
        async def switch_screen(index):
            content_area.content = screens[index]
            if index == 5:
                page.update(); return
            if index == 0: nav.selected_index = 0
            elif index in (1, 2): nav.selected_index = 1
            elif index == 3: 
                nav.selected_index = 2
                await refresh_lesson_groups()
            elif index == 4: 
                nav.selected_index = 3
                await refresh_stats_groups()
            if index == 1: await refresh_groups()
            if index == 2: await refresh_students()
            page.update()

        def on_nav(e):
            page.run_task(switch_screen, [0, 1, 3, 4][e.control.selected_index])

        def open_group(gid, gname):
            current_group_id["value"] = gid
            students_title.value = f"👥 {gname}"
            page.run_task(switch_screen, 2)

        async def logout(e):
            await asyncio.to_thread(db.sign_out)
            state["user"] = None
            state["view"] = "login"
            render()

        nav = ft.NavigationRail(
            selected_index=0, label_type=ft.NavigationRailLabelType.ALL, min_width=100,
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME, label="Главная"),
                ft.NavigationRailDestination(icon=ft.Icons.PEOPLE_OUTLINED, selected_icon=ft.Icons.PEOPLE, label="Группы"),
                ft.NavigationRailDestination(icon=ft.Icons.CALENDAR_MONTH_OUTLINED, selected_icon=ft.Icons.CALENDAR_MONTH, label="Занятие"),
                ft.NavigationRailDestination(icon=ft.Icons.BAR_CHART_OUTLINED, selected_icon=ft.Icons.BAR_CHART, label="Статистика"),
            ], on_change=on_nav,
        )

        page.run_task(refresh_groups)

        top_bar = ft.Container(
            content=ft.Row([
                ft.Text(f"👤 {user['email']} ({user['role']})", color=ft.Colors.GREY, size=12),
                ft.TextButton("Выйти", icon=ft.Icons.LOGOUT, on_click=logout),
            ], alignment=ft.MainAxisAlignment.END),
            padding=5, bgcolor=ft.Colors.GREY_100,
        )

        return ft.Column([
            top_bar, ft.Row([nav, ft.VerticalDivider(width=1), content_area], expand=True, spacing=0),
        ], expand=True, spacing=0)

    # ==========================================================
    # ПРИЛОЖЕНИЕ СТУДЕНТА
    # ==========================================================
    def build_student_app():
        user = state["user"]
        att_list = ft.Column(spacing=8)
        summary = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        status_msg = ft.Text("", color=ft.Colors.BLUE)

        # Делаем асинхронным!
        async def refresh():
            att_list.controls.clear()
            try:
                rows = await asyncio.to_thread(db.get_student_attendance, user["id"])
                if not rows:
                    summary.value = "Занятий пока не было."
                    summary.color = ft.Colors.GREY
                    page.update()
                    return
                    
                present = sum(1 for r in rows if r["status"] == "present")
                total = len(rows)
                p = round(present / total * 100, 1) if total else 0
                summary.value = f"📊 Посещаемость: {p}% ({present} из {total})"
                summary.color = ft.Colors.GREEN if p >= 80 else ft.Colors.ORANGE if p >= 60 else ft.Colors.RED

                for r in rows:
                    date_str = r["lessons"]["created_at"][:16].replace("T", " ")
                    att_list.controls.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN),
                            ft.Text(f"{date_str}", weight=ft.FontWeight.BOLD),
                        ]), padding=12, bgcolor=ft.Colors.GREY_100, border_radius=8))
            except:
                summary.value = "Ошибка загрузки (нет сети)"
                summary.color = ft.Colors.RED
            page.update()

        active_camera = {"ref": None}

        async def scan_qr(e):
            status_msg.value = "Запрос доступа к камере и GPS..."
            status_msg.color = ft.Colors.BLUE
            page.update()

            geo = fg.Geolocator()
            try:
                pos = await geo.get_current_position_async()
                student_lat = pos.latitude if pos else None
                student_lon = pos.longitude if pos else None
            except Exception:
                student_lat, student_lon = None, None

            camera = fc.Camera(expand=True, on_stream_image=False)
            active_camera["ref"] = camera

            async def capture_and_scan(e):
                try:
                    picture = await camera.take_picture()
                    image = Image.open(io.BytesIO(picture))
                    decoded_objects = decode(image)
                    
                    if decoded_objects:
                        qr_data = decoded_objects[0].data.decode("utf-8")
                        page.pop_dialog() # Исправлено на pop_dialog
                        await handle_qr_data(qr_data, student_lat, student_lon)
                    else:
                        status_msg.value = "QR-код не найден. Попробуйте еще раз."
                        status_msg.color = ft.Colors.ORANGE
                        page.update()
                except Exception as ex:
                    status_msg.value = f"Ошибка сканирования: {ex}"
                    status_msg.color = ft.Colors.RED
                    page.update()

            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Наведите камеру на QR-код и нажмите 'Сканировать'"),
                content=camera,
                actions=[
                    ft.Button("Сканировать", on_click=capture_and_scan),
                    ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog()) # Исправлено на pop_dialog
                ]
            ))

        async def handle_qr_data(qr_data, student_lat, student_lon):
            status_msg.value = "QR распознан! Проверяю геолокацию..."
            status_msg.color = ft.Colors.BLUE
            page.update()

            parts = qr_data.split(":")
            lesson_id = parts[0]
            qr_timestamp = parts[1] if len(parts) > 1 else "0"

            try:
                lesson_lat, lesson_lon = await asyncio.to_thread(db.get_lesson_coords, lesson_id)
                
                is_close = True
                if lesson_lat and lesson_lon and student_lat and student_lon:
                    R = 6371000
                    phi1, phi2 = math.radians(lesson_lat), math.radians(student_lat)
                    dphi = math.radians(student_lat - lesson_lat)
                    dlambda = math.radians(student_lon - lesson_lon)
                    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
                    distance = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))
                    
                    if distance > 70:
                        is_close = False

                if not is_close:
                    status_msg.value = "❌ Вы находитесь слишком далеко от аудитории!"
                    status_msg.color = ft.Colors.RED
                    page.update()
                    return
                
                success, msg = await asyncio.to_thread(db.mark_student_present, lesson_id, user["id"], qr_timestamp)
                if success:
                    status_msg.value = "✅ " + msg
                    status_msg.color = ft.Colors.GREEN
                    await refresh()
                else:
                    status_msg.value = "❌ Ошибка: " + msg
                    status_msg.color = ft.Colors.RED
            except:
                status_msg.value = "❌ Ошибка сети при отметке"
                status_msg.color = ft.Colors.RED
            page.update()

        async def logout(e):
            await asyncio.to_thread(db.sign_out)
            state["user"] = None
            state["view"] = "login"
            render()

        top_bar = ft.Container(
            content=ft.Row([
                ft.Text(f"👤 {user['email']}", color=ft.Colors.GREY, size=12),
                ft.TextButton("Выйти", icon=ft.Icons.LOGOUT, on_click=logout),
            ], alignment=ft.MainAxisAlignment.END),
            padding=5, bgcolor=ft.Colors.GREY_100,
        )

        page.run_task(refresh)

        return ft.Column([
            top_bar,
            ft.Container(
                content=ft.Column([
                    ft.Text(f"👋 Здравствуйте, {user['full_name']}!", size=26, weight=ft.FontWeight.BOLD),
                    ft.Button("📷 Отметиться на занятии", icon=ft.Icons.QR_CODE_SCANNER, on_click=scan_qr, height=50),
                    status_msg,
                    ft.Divider(), 
                    ft.Text("Моя посещаемость", size=20, weight=ft.FontWeight.BOLD),
                    summary, att_list,
                ], spacing=15, scroll=ft.ScrollMode.AUTO),
                padding=30, expand=True,
            ),
        ], expand=True, spacing=0)

    # ==========================================================
    # ПАНЕЛЬ АДМИНИСТРАТОРА
    # ==========================================================
    def build_admin_app():
        user = state["user"]
        
        search_field = ft.TextField(label="Поиск по ФИО", width=400, hint_text="Введите имя...")
        students_list = ft.Column(spacing=10)

        async def refresh_students(e=None):
            students_list.controls.clear()
            query = search_field.value.strip() if search_field.value else ""
            try:
                students = await asyncio.to_thread(db.get_all_students_for_admin, query)
                
                if not students:
                    students_list.controls.append(ft.Text("Студенты не найдены.", italic=True, color=ft.Colors.GREY))
                    page.update()
                    return

                for s in students:
                    device_status = "✅ Привязан" if s.get("device_id") else "❌ Не привязан"
                    reset_count = s.get("device_reset_count", 0)
                    group_name = s["groups"]["name"] if s.get("groups") else "Нет группы"
                    
                    count_text = f"⚠️ Сбросов: {reset_count}" if reset_count > 0 else "Сбросов: 0"
                    count_color = ft.Colors.RED if reset_count > 0 else ft.Colors.GREY

                    def make_reset_handler(sid):
                        def reset_dev(e):
                            page.run_task(do_reset, sid)
                        return reset_dev

                    students_list.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.PERSON),
                                    ft.Text(s["full_name"], weight=ft.FontWeight.BOLD, size=16, expand=True),
                                    ft.Text(f"({group_name})", color=ft.Colors.GREY, size=14),
                                ]),
                                ft.Row([
                                    ft.Text(f"Email: {s['email']}", size=12),
                                    ft.Text(f"| Телефон: {device_status}", size=12),
                                    ft.Text(f"| {count_text}", size=12, color=count_color),
                                    ft.Button(
                                        "🔄 Сбросить телефон", 
                                        on_click=make_reset_handler(s["id"]),
                                        style=ft.ButtonStyle(bgcolor=ft.Colors.ORANGE_100, color=ft.Colors.ORANGE_900)
                                    )
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                            ]),
                            padding=15, bgcolor=ft.Colors.BLUE_50, border_radius=8,
                            border=ft.border.all(1, ft.Colors.BLUE_200)
                        )
                    )
            except:
                students_list.controls.append(ft.Text("Ошибка сети", color=ft.Colors.RED))
            page.update()

        async def do_reset(sid):
            try:
                if await asyncio.to_thread(db.reset_student_device, sid):
                    page.show_dialog(ft.SnackBar(ft.Text("Устройство успешно сброшено!"), bgcolor=ft.Colors.GREEN))
                    await refresh_students()
            except:
                pass

        search_field.on_change = lambda e: page.run_task(refresh_students)
        
        async def logout(e):
            await asyncio.to_thread(db.sign_out)
            state["user"] = None
            state["view"] = "login"
            render()

        top_bar = ft.Container(
            content=ft.Row([
                ft.Text(f"👤 {user['email']} (Администратор)", color=ft.Colors.GREY, size=12),
                ft.TextButton("Выйти", icon=ft.Icons.LOGOUT, on_click=logout),
            ], alignment=ft.MainAxisAlignment.END),
            padding=5, bgcolor=ft.Colors.GREY_100,
        )

        page.run_task(refresh_students)

        return ft.Column([
            top_bar,
            ft.Container(
                content=ft.Column([
                    ft.Text("🏛️ Панель Администратора", size=28, weight=ft.FontWeight.BOLD),
                    ft.Text("Здесь вы можете управлять устройствами студентов.", color=ft.Colors.GREY),
                    ft.Divider(),
                    ft.Row([search_field, ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: page.run_task(refresh_students))]),
                    students_list
                ], spacing=15, scroll=ft.ScrollMode.AUTO),
                padding=30, expand=True,
            ),
        ], expand=True, spacing=0)

    def render():
        if state["user"] is None:
            root.content = build_login() if state["view"] == "login" else build_register()
        else:
            role = state["user"]["role"]
            if role == "admin":
                root.content = build_admin_app()
            elif role == "teacher":
                root.content = build_teacher_app()
            else:
                root.content = build_student_app()
        page.update()

    page.add(root)
    render()

if __name__ == "__main__":
    ft.run(main)
