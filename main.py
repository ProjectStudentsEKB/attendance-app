import flet_permission_handler as fph
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
        email_field = ft.TextField(label="Email", expand=True)
        password_field = ft.TextField(label="Пароль", password=True, can_reveal_password=True, expand=True)
        error_text = ft.Text("", color=ft.Colors.RED)
        
        login_btn = ft.Button("Войти", expand=True)
        loading_ring = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        
        async def on_login(e):
            error_text.value = ""
            if not email_field.value or not password_field.value:
                error_text.value = "Заполни все поля"
                page.update()
                return
            
            login_btn.content = ft.Row([ft.Text("Подождите...", color=ft.Colors.WHITE), loading_ring], alignment=ft.MainAxisAlignment.CENTER)
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
                error_text.value = f"Ошибка сети: {ex}"
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
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=10, scroll=ft.ScrollMode.AUTO),
            alignment=ft.Alignment.CENTER, expand=True, padding=30,
        )

    # ==========================================================
    # ЭКРАН РЕГИСТРАЦИИ
    # ==========================================================
    def build_register():
        current_role = state["reg_role"]
        
        email_field = ft.TextField(label="Email", expand=True, value=state["reg_email"])
        password_field = ft.TextField(label="Пароль (мин. 6 символов)", password=True, can_reveal_password=True, expand=True, value=state["reg_password"])
        
        def on_role_change(e):
            state["reg_role"] = e.control.value
            state["reg_email"] = email_field.value
            state["reg_password"] = password_field.value
            render() 

        role_dropdown = ft.Dropdown(
            label="Кто вы?", expand=True, value=current_role,
            options=[
                ft.DropdownOption(key="student", text="Студент"),
                ft.DropdownOption(key="teacher", text="Преподаватель"),
            ],
            on_select=on_role_change
        )

        error_text = ft.Text("", color=ft.Colors.RED)
        
        register_btn = ft.Button("Зарегистрироваться", expand=True)
        loading_ring = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

        if current_role == "student":
            group_dd = ft.Dropdown(label="Выберите группу", expand=True)
            student_dd = ft.Dropdown(label="Выберите свое ФИО", expand=True)
            code_field = ft.TextField(label="Персональный код (из деканата)", expand=True)
            
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

                if len(password) < 6:
                    error_text.value = "Пароль должен быть не менее 6 символов."
                    page.update()
                    return

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

                    await asyncio.to_thread(db.bind_device, new_user_id, device_id)
                    await asyncio.to_thread(db.sign_in, email, password)
                    state["user"] = await asyncio.to_thread(db.get_profile)
                    state["reg_role"] = "student"
                    render()
                except Exception as ex:
                    error_text.value = f"Ошибка: {ex}"
                    register_btn.content = "Зарегистрироваться"
                    register_btn.disabled = False
                    loading_ring.visible = False
                    page.update()

            form_fields = [group_dd, student_dd, code_field]
            register_btn.on_click = on_register

        else:
            full_name_field = ft.TextField(label="ФИО Преподавателя", expand=True)
            teacher_code_field = ft.TextField(label="Секретный код преподавателя", password=True, can_reveal_password=True, expand=True)

            async def on_register(e):
                error_text.value = ""
                email = (email_field.value or "").strip()
                password = password_field.value or ""
                f_name = (full_name_field.value or "").strip()
                t_code = (teacher_code_field.value or "").strip()

                if len(password) < 6:
                    error_text.value = "Пароль должен быть не менее 6 символов."
                    page.update()
                    return

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
                        await asyncio.to_thread(db.bind_device, state["user"]["id"], device_id)
                        state["reg_role"] = "student"
                        render()
                    else:
                        error_text.value = "Эта почта уже зарегистрирована." if "User already registered" in str(result) else f"Ошибка: {result}"
                        register_btn.content = "Зарегистрироваться"
                        register_btn.disabled = False
                        loading_ring.visible = False
                        page.update()
                except Exception as ex:
                    error_text.value = f"Ошибка: {ex}"
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
                email_field, password_field, role_dropdown, *form_fields, error_text, register_btn,
                ft.TextButton("Уже есть аккаунт? Войти", on_click=goto_login),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=10, scroll=ft.ScrollMode.AUTO),
            alignment=ft.Alignment.CENTER, expand=True, padding=30,
        )

    # ==========================================================
    # ПРИЛОЖЕНИЕ ПРЕПОДАВАТЕЛЯ
    # ==========================================================
    def build_teacher_app():
        user = state["user"]
        current_group_id = {"value": None}

        home_screen = ft.Column([ft.Text(f"🏠 Здравствуйте, {user['full_name']}!", size=26, weight=ft.FontWeight.BOLD)], spacing=20)

        group_name_field = ft.TextField(label="Название группы", hint_text="ИС-21", expand=True)
        groups_list = ft.Column(spacing=10)

        async def refresh_groups():
            groups_list.controls.clear()
            groups_list.controls.append(ft.Text("Подождите, идет загрузка групп...", color=ft.Colors.BLUE))
            page.update()
            try:
                groups = await asyncio.to_thread(db.get_groups)
                groups_list.controls.clear()
                if not groups:
                    groups_list.controls.append(ft.Text("Нет групп. Добавь первую!", color=ft.Colors.GREY))
                else:
                    for g in groups:
                        students = await asyncio.to_thread(db.get_students, g["id"])
                        groups_list.controls.append(ft.Container(
                            content=ft.Row([ft.Icon(ft.Icons.PEOPLE), ft.Text(g["name"], size=18, weight=ft.FontWeight.BOLD), ft.Text(f"{len(students)} студ.", color=ft.Colors.GREY), ft.Icon(ft.Icons.CHEVRON_RIGHT)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            padding=15, bgcolor=ft.Colors.BLUE_50, border_radius=8, on_click=lambda e, gid=g["id"], n=g["name"]: open_group(gid, n), ink=True))
            except:
                groups_list.controls.clear()
                groups_list.controls.append(ft.Text("Ошибка загрузки. Проверьте сеть.", color=ft.Colors.RED))
            page.update()

        async def on_add_group(e):
            name = (group_name_field.value or "").strip()
            if not name: return
            try:
                if await asyncio.to_thread(db.add_group, name):
                    group_name_field.value = ""
                    await refresh_groups()
            except: pass
            page.update()

        groups_screen = ft.Column([ft.Text("👥 Группы", size=28, weight=ft.FontWeight.BOLD), ft.Row([group_name_field, ft.Button("Добавить", icon=ft.Icons.ADD, on_click=on_add_group)]), ft.Divider(), groups_list], scroll=ft.ScrollMode.AUTO)

        students_title = ft.Text("", size=28, weight=ft.FontWeight.BOLD)
        students_list = ft.Column(spacing=10)

        async def refresh_students():
            students_list.controls.clear()
            gid = current_group_id["value"]
            if gid is None: return
            try:
                students = await asyncio.to_thread(db.get_students, gid)
                for s in students:
                    students_list.controls.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.PERSON), ft.Text(s["full_name"], size=16)]), padding=10, bgcolor=ft.Colors.GREEN_50, border_radius=8))
            except: pass
            page.update()

        students_screen = ft.Column([ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: page.run_task(switch_screen, 1)), students_title]), ft.Divider(), students_list], scroll=ft.ScrollMode.AUTO)

        lesson_group_dd = ft.Dropdown(label="Группа", expand=True, options=[])
        lesson_status = ft.Text("", weight=ft.FontWeight.BOLD)
        
        qr_lesson_id = {"value": None}
        qr_lesson_info = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        BLANK_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        qr_image = ft.Image(src=BLANK_IMG, height=250, fit=ft.BoxFit.CONTAIN)
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
            except: pass
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
            if qr_lesson_id["value"] is None or not lesson_group_dd.value: return
            try:
                all_students = await asyncio.to_thread(db.get_students, lesson_group_dd.value)
                present_ids = await asyncio.to_thread(db.get_attendance, qr_lesson_id["value"])
                qr_attendees_count.value = f"✅ Отметились: {len(present_ids)} из {len(all_students)}"
                for sid in present_ids:
                    name = next((s["full_name"] for s in all_students if s["id"] == sid), "—")
                    qr_attendees_list.controls.append(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=16), ft.Text(name, size=13)]))
            except: pass
            page.update()

        async def qr_loop():
            while qr_auto_thread["running"]:
                await asyncio.sleep(10)
                if qr_lesson_id["value"] is None: break
                try: 
                    refresh_qr()
                    await refresh_attendees()
                except: break
            qr_auto_thread["running"] = False

        def start_qr_auto_refresh():
            if qr_auto_thread["running"]: return
            qr_auto_thread["running"] = True
            page.run_task(qr_loop)

        def stop_qr_auto_refresh(): qr_auto_thread["running"] = False

        async def on_start_lesson(e):
            if not lesson_group_dd.value: return
            lat, lon = None, None
            try:
                geo = fg.Geolocator()
                pos = await geo.get_current_position_async()
                lat = pos.latitude if pos else None
                lon = pos.longitude if pos else None
            except: pass
            
            try:
                gid = lesson_group_dd.value
                lid = await asyncio.to_thread(db.start_lesson, gid, user["id"], lat, lon)
                qr_lesson_id["value"] = lid
                gname = next((opt.text for opt in lesson_group_dd.options if opt.key == gid), "Группа")
                qr_lesson_info.value = f"Группа: {gname} | Начато: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                await switch_screen(5)
                refresh_qr()
                await refresh_attendees()
                start_qr_auto_refresh()
            except Exception as ex:
                lesson_status.value = f"Ошибка: {ex}"
                lesson_status.color = ft.Colors.RED
                page.update()

        async def on_mark_all(e):
            if qr_lesson_id["value"] is None or not lesson_group_dd.value: return
            try:
                students = await asyncio.to_thread(db.get_students, lesson_group_dd.value)
                if students:
                    await asyncio.to_thread(db.mark_all_present, qr_lesson_id["value"], [s["id"] for s in students])
                    await refresh_attendees()
            except: pass

        async def on_finish_lesson(e):
            stop_qr_auto_refresh()
            if qr_lesson_id["value"]:
                try: await asyncio.to_thread(db.finish_lesson, qr_lesson_id["value"])
                except: pass
            qr_lesson_id["value"] = None
            await switch_screen(3)

        lesson_screen = ft.Column([
            ft.Text("📅 Занятие", size=28, weight=ft.FontWeight.BOLD), ft.Divider(), ft.Row([lesson_group_dd]),
            ft.Button("▶  Начать занятие", icon=ft.Icons.PLAY_ARROW, on_click=on_start_lesson, style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE), expand=True),
            lesson_status,
        ], scroll=ft.ScrollMode.AUTO)

        qr_screen = ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: (stop_qr_auto_refresh(), page.run_task(switch_screen, 3))), ft.Text("📱 QR-код", size=22, weight=ft.FontWeight.BOLD)]),
            qr_lesson_info, 
            ft.Container(content=qr_image, alignment=ft.Alignment.CENTER, padding=5),
            ft.Row([qr_countdown, ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: (refresh_qr(), page.run_task(refresh_attendees)))], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.Column([
                qr_attendees_count, qr_attendees_list,
                ft.Column([
                    ft.Button("✅ Отметить вручную", on_click=on_mark_all, width=320),
                    ft.Button("⏹ Завершить", icon=ft.Icons.STOP, on_click=on_finish_lesson, style=ft.ButtonStyle(bgcolor=ft.Colors.RED_400, color=ft.Colors.WHITE), width=320),
                ], spacing=10, alignment=ft.MainAxisAlignment.CENTER)
            ], expand=True, scroll=ft.ScrollMode.AUTO)
        ], expand=True)

        # ---- СТАТИСТИКА ----
        stats_group_dd = ft.Dropdown(label="Группа", expand=True)
        stats_student_dd = ft.Dropdown(label="Студент (необязательно)", expand=True, options=[ft.dropdown.Option(key="", text="Все студенты")])
        stats_period_dd = ft.Dropdown(label="Период", expand=True, value="30", options=[
            ft.dropdown.Option(key="7", text="Последняя неделя"),
            ft.dropdown.Option(key="30", text="Последний месяц"),
            ft.dropdown.Option(key="60", text="Последние 2 месяца"),
            ft.dropdown.Option(key="90", text="Последние 3 месяца"),
            ft.dropdown.Option(key="120", text="Последние 4 месяца"),
        ])
        stats_summary = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        stats_list = ft.Column(spacing=8)

        async def refresh_stats_groups():
            stats_group_dd.options.clear()
            groups = await asyncio.to_thread(db.get_groups)
            for g in groups: stats_group_dd.options.append(ft.dropdown.Option(key=g["id"], text=g["name"]))
            page.update()

        async def on_stats_group_change(e):
            stats_student_dd.options.clear()
            stats_student_dd.options.append(ft.dropdown.Option(key="", text="Все студенты"))
            stats_student_dd.value = ""
            if stats_group_dd.value:
                students = await asyncio.to_thread(db.get_students, stats_group_dd.value)
                for s in students: stats_student_dd.options.append(ft.dropdown.Option(key=s["id"], text=s["full_name"]))
            page.update()
        stats_group_dd.on_select = lambda e: page.run_task(on_stats_group_change, e)

        def color_for(p):
            if p >= 80: return ft.Colors.GREEN, ft.Colors.GREEN_50
            elif p >= 60: return ft.Colors.ORANGE, ft.Colors.ORANGE_50
            return ft.Colors.RED, ft.Colors.RED_50

        async def refresh_my_stats(e=None):
            stats_list.controls.clear()
            stats_summary.value = "Загрузка..."
            page.update()
            try:
                gid = stats_group_dd.value if stats_group_dd.value else None
                sid = stats_student_dd.value if stats_student_dd.value else None
                days = int(stats_period_dd.value)
                
                stats, total = await asyncio.to_thread(db.get_teacher_custom_stats, user["id"], gid, sid, days)
                if total == 0:
                    stats_summary.value = "⚠️ Нет занятий за выбранный период."
                    page.update()
                    return
                stats_summary.value = f"📊 Занятий: {total}"
                for s in stats:
                    color, bg = color_for(s["percent"])
                    stats_list.controls.append(ft.Container(
                        content=ft.Row([ft.Text(s["name"], expand=True), ft.Text(f"{s['percent']}%", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)]),
                        padding=10, bgcolor=color, border_radius=8))
            except Exception as ex:
                stats_summary.value = f"Ошибка: {ex}"
            page.update()

        def clear_stats(e):
            stats_group_dd.value = None
            stats_student_dd.value = None
            stats_list.controls.clear()
            stats_summary.value = ""
            page.update()

        def export_report(e):
            report = f"📊 ОТЧЕТ (Период: {stats_period_dd.value} дней)\n\n"
            for c in stats_list.controls:
                report += f"{c.content.controls[0].value} | {c.content.controls[1].value}\n"
            page.set_clipboard(report)
            page.show_dialog(ft.SnackBar(ft.Text("Отчет скопирован в буфер обмена (вставьте в WhatsApp)!")))

        stats_screen = ft.Column([
            ft.Text("📊 Моя статистика", size=28, weight=ft.FontWeight.BOLD),
            ft.Row([stats_group_dd]),
            ft.Row([stats_student_dd]),
            ft.Row([stats_period_dd]),
            ft.Row([
                ft.Button("Показать", on_click=refresh_my_stats, expand=True),
                ft.Button("Сброс", on_click=clear_stats, expand=True),
                ft.Button("Копировать", on_click=export_report, expand=True),
            ]),
            ft.Divider(), stats_summary, stats_list
        ], scroll=ft.ScrollMode.AUTO)

        screens = [home_screen, groups_screen, students_screen, lesson_screen, stats_screen, qr_screen]
        content_area = ft.Container(content=screens[0], padding=20, expand=True)

        async def switch_screen(index):
            content_area.content = screens[index]
            if index == 5: page.update(); return
            if index == 0: nav.selected_index = 0
            elif index in (1, 2): nav.selected_index = 1
            elif index == 3: nav.selected_index = 2; await refresh_lesson_groups()
            elif index == 4: nav.selected_index = 3; await refresh_my_stats()
            if index == 1: await refresh_groups()
            if index == 2: await refresh_students()
            page.update()

        def on_nav(e): page.run_task(switch_screen, [0, 1, 3, 4][e.control.selected_index])
        def open_group(gid, gname): current_group_id["value"] = gid; students_title.value = f"👥 {gname}"; page.run_task(switch_screen, 2)
        
        async def logout(e): await asyncio.to_thread(db.sign_out); state["user"] = None; state["view"] = "login"; render()

        nav = ft.NavigationRail(selected_index=0, label_type=ft.NavigationRailLabelType.NONE, min_width=60, destinations=[ft.NavigationRailDestination(icon=ft.Icons.HOME, label="Главная"), ft.NavigationRailDestination(icon=ft.Icons.PEOPLE, label="Группы"), ft.NavigationRailDestination(icon=ft.Icons.CALENDAR_MONTH, label="Занятие"), ft.NavigationRailDestination(icon=ft.Icons.BAR_CHART, label="Статистика")], on_change=on_nav)
        page.run_task(refresh_groups)

        top_bar = ft.Container(content=ft.Row([ft.Text(f"👤 {user['email']}"), ft.TextButton("Выйти", on_click=logout)], alignment=ft.MainAxisAlignment.END), bgcolor=ft.Colors.GREY_100)
        return ft.Column([
            top_bar, 
            ft.Row([nav, ft.VerticalDivider(width=1), content_area], expand=True, spacing=0)
        ], expand=True, spacing=0)

    # ==========================================================
    # ПРИЛОЖЕНИЕ СТУДЕНТА (СКАНЕР РАБОТАЕТ)
    # ==========================================================
    def build_student_app():
        user = state["user"]
        att_list = ft.Column(spacing=8)
        summary = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        status_msg = ft.Text("", color=ft.Colors.BLUE)

        async def refresh():
            att_list.controls.clear()
            try:
                rows = await asyncio.to_thread(db.get_student_attendance, user["id"])
                if not rows:
                    summary.value = "Занятий пока не было."
                    page.update()
                    return
                present = sum(1 for r in rows if r["status"] == "present")
                p = round(present / len(rows) * 100, 1)
                summary.value = f"📊 Посещаемость: {p}% ({present} из {len(rows)})"
                for r in rows:
                    date_str = r["lessons"]["created_at"][:16].replace("T", " ")
                    att_list.controls.append(ft.Container(content=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN), ft.Text(date_str)]), padding=10, bgcolor=ft.Colors.GREY_100, border_radius=8))
            except: pass
            page.update()

        async def scan_qr(e):
            status_msg.value = "Запрос доступа к камере и GPS..."
            page.update()

            ph = fph.PermissionHandler()
            page.services.append(ph)
            try:
                await ph.request(fph.Permission.CAMERA)
            except Exception as ex:
                status_msg.value = f"Нет разрешения: {ex}"
                page.update()
                return

            geo = fg.Geolocator()
            try:
                pos = await geo.get_current_position_async()
                student_lat = pos.latitude if pos else None
                student_lon = pos.longitude if pos else None
            except Exception:
                student_lat, student_lon = None, None

            camera = fc.Camera(preview_enabled=True, width=350, height=400)
            dialog_status = ft.Text("", color=ft.Colors.RED, weight=ft.FontWeight.BOLD)

            async def capture_and_scan(e):
                dialog_status.value = "Сканирование..."
                page.update()
                try:
                    picture = await camera.take_picture()
                    image = Image.open(io.BytesIO(picture))
                    decoded_objects = decode(image)
                    
                    if not decoded_objects:
                        dialog_status.value = "❌ QR-код не распознан."
                        page.update()
                        return
                    
                    qr_data = decoded_objects[0].data.decode("utf-8")
                    parts = qr_data.split(":")
                    if len(parts) != 2:
                        dialog_status.value = "❌ Неверный формат."
                        page.update()
                        return
                    
                    lesson_id = parts[0]
                    lesson = await asyncio.to_thread(db.get_lesson_details, lesson_id)
                    
                    if not lesson or not lesson["is_active"]:
                        dialog_status.value = "❌ Занятие неактивно."
                        page.update()
                        return
                    
                    page.pop_dialog()
                    page.update()
                    await handle_qr_data(qr_data, student_lat, student_lon, lesson["latitude"], lesson["longitude"])

                except Exception as ex:
                    dialog_status.value = f"❌ Ошибка: {ex}"
                    page.update()

            page.show_dialog(ft.AlertDialog(
                title=ft.Text("Наведите камеру на QR"),
                content=ft.Column([camera, dialog_status], tight=True),
                actions=[ft.Button("Сканировать", on_click=capture_and_scan), ft.TextButton("Отмена", on_click=lambda e: page.pop_dialog())]
            ))
            page.update()

            try:
                cameras = await camera.get_available_cameras()
                if cameras:
                    await camera.initialize(description=cameras[0], resolution_preset=fc.ResolutionPreset.MEDIUM)
            except Exception as ex:
                dialog_status.value = f"Ошибка камеры: {ex}"
                page.update()

        async def handle_qr_data(qr_data, student_lat, student_lon, lesson_lat, lesson_lon):
            status_msg.value = "Проверяю геолокацию..."
            page.update()
            parts = qr_data.split(":")
            lesson_id, qr_timestamp = parts[0], parts[1]
            try:
                if lesson_lat and lesson_lon and student_lat and student_lon:
                    R = 6371000
                    phi1, phi2 = math.radians(lesson_lat), math.radians(student_lat)
                    dphi = math.radians(student_lat - lesson_lat)
                    dlambda = math.radians(student_lon - lesson_lon)
                    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
                    distance = 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))
                    if distance > 70:
                        status_msg.value = "❌ Слишком далеко от аудитории!"
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
            except Exception as ex:
                status_msg.value = f"❌ Ошибка БД: {ex}"
                status_msg.color = ft.Colors.RED
            page.update()

        async def logout(e): await asyncio.to_thread(db.sign_out); state["user"] = None; state["view"] = "login"; render()

        top_bar = ft.Container(content=ft.Row([ft.Text(f"👤 {user['email']}"), ft.TextButton("Выйти", on_click=logout)], alignment=ft.MainAxisAlignment.END), bgcolor=ft.Colors.GREY_100)
        page.run_task(refresh)

        return ft.Column([
            top_bar,
            ft.Container(
                content=ft.Column([
                    ft.Text(f"👋 Здравствуйте, {user['full_name']}!", size=26, weight=ft.FontWeight.BOLD),
                    ft.Button("📷 Отметиться на занятии", icon=ft.Icons.QR_CODE_SCANNER, on_click=scan_qr, height=50),
                    status_msg, ft.Divider(), ft.Text("Моя посещаемость", size=20), summary, att_list,
                ], spacing=15, scroll=ft.ScrollMode.AUTO),
                padding=30, expand=True,
            ),
        ], expand=True, spacing=0)

    # ==========================================================
    # ПАНЕЛЬ АДМИНИСТРАТОРА (Упрощенная)
    # ==========================================================
    def build_admin_app():
        user = state["user"]
        search_field = ft.TextField(label="Поиск по ФИО", expand=True)
        students_list = ft.Column(spacing=10)

        async def refresh_students(e=None):
            students_list.controls.clear()
            query = search_field.value.strip() if search_field.value else ""
            try:
                students = await asyncio.to_thread(db.get_all_students_for_admin, query)
                for s in students:
                    device_status = "✅" if s.get("device_id") else "❌"
                    group_name = s["groups"]["name"] if s.get("groups") else "Нет группы"
                    students_list.controls.append(ft.Container(content=ft.Row([ft.Text(s["full_name"], expand=True), ft.Text(f"({group_name})"), ft.Text(f"Тел: {device_status}"), ft.Button("Сбросить", on_click=lambda e, sid=s["id"]: page.run_task(do_reset, sid))])))
            except: pass
            page.update()

        async def do_reset(sid):
            if await asyncio.to_thread(db.reset_student_device, sid):
                page.show_dialog(ft.SnackBar(ft.Text("Сброшено!")))
                await refresh_students()

        search_field.on_change = lambda e: page.run_task(refresh_students)
        screen_students = ft.Column([ft.Row([search_field, ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: page.run_task(refresh_students))]), students_list], scroll=ft.ScrollMode.AUTO, expand=True)

        prog_dd = ft.Dropdown(label="Программа", expand=True, options=[ft.DropdownOption(key="", text="Все программы")])
        for p in db.get_all_programs(): prog_dd.options.append(ft.DropdownOption(key=p, text=p))
        student_search = ft.TextField(label="Студент (ФИО)", expand=True)
        a_start_date = ft.TextField(label="С даты", hint_text="2026-10-01", expand=True)
        a_end_date = ft.TextField(label="По дату", hint_text="2026-12-31", expand=True)
        a_summary = ft.Text("", weight=ft.FontWeight.BOLD)
        a_list = ft.Column(spacing=8)

        def color_for(p):
            if p >= 80: return ft.Colors.GREEN
            return ft.Colors.RED

        async def refresh_admin_stats(e=None):
            a_list.controls.clear()
            a_summary.value = "Анализ..."
            page.update()
            try:
                prog = prog_dd.value if prog_dd.value else None
                stud = student_search.value.strip() if student_search.value else None
                s_date = a_start_date.value if a_start_date.value else None
                e_date = a_end_date.value if a_end_date.value else None
                stats, total = await asyncio.to_thread(db.get_admin_stats, None, prog, stud, s_date, e_date)
                if total == 0:
                    a_summary.value = "Нет данных."
                    page.update()
                    return
                a_summary.value = f"📊 Занятий: {total}"
                for s in stats:
                    a_list.controls.append(ft.Container(content=ft.Row([ft.Text(s["full_name"], expand=True), ft.Text(f"{s['percent']}%", color=color_for(s["percent"]))]), padding=10, bgcolor=ft.Colors.GREY_100))
            except Exception as ex:
                a_summary.value = f"Ошибка: {ex}"
            page.update()

        def export_admin_report(e):
            report = "🏛️ ОТЧЕТ\n"
            for c in a_list.controls:
                report += f"{c.content.controls[0].value} | {c.content.controls[1].value}\n"
            page.set_clipboard(report)
            page.show_dialog(ft.SnackBar(ft.Text("Отчет скопирован!")))

        screen_stats = ft.Column([
            ft.Row([prog_dd]), ft.Row([student_search]), ft.Row([a_start_date, a_end_date], spacing=5),
            ft.Row([ft.Button("Найти", on_click=refresh_admin_stats, expand=True), ft.Button("Копировать", on_click=export_admin_report, expand=True)]),
            ft.Divider(), a_summary, a_list
        ], scroll=ft.ScrollMode.AUTO, expand=True)

        content_area = ft.Container(content=screen_students, expand=True, padding=10)
        
        def change_tab(e):
            idx = e.control.selected_index
            content_area.content = screen_students if idx == 0 else screen_stats
            if idx == 0: page.run_task(refresh_students)
            page.update()

        admin_nav = ft.NavigationRail(selected_index=0, label_type=ft.NavigationRailLabelType.NONE, min_width=60, destinations=[ft.NavigationRailDestination(icon=ft.Icons.PEOPLE, label="Студенты"), ft.NavigationRailDestination(icon=ft.Icons.ANALYTICS, label="Статистика")], on_change=change_tab)
        
        async def logout(e): await asyncio.to_thread(db.sign_out); state["user"] = None; state["view"] = "login"; render()

        top_bar = ft.Container(content=ft.Row([ft.Text(f"👤 Админ"), ft.TextButton("Выйти", on_click=logout)]), bgcolor=ft.Colors.GREY_100)
        page.run_task(refresh_students)
        
        return ft.Column([
            top_bar, 
            ft.Row([admin_nav, ft.VerticalDivider(width=1), content_area], expand=True, spacing=0) # Убрали scroll
        ], expand=True, spacing=0) # Убрали scroll
        
    def render():
        if state["user"] is None:
            root.content = build_login() if state["view"] == "login" else build_register()
        else:
            role = state["user"]["role"]
            if role == "admin": root.content = build_admin_app()
            elif role == "teacher": root.content = build_teacher_app()
            else: root.content = build_student_app()
        page.update()

    page.add(root)
    render()

if __name__ == "__main__":
    ft.run(main)
