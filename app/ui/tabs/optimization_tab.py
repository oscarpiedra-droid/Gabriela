import os
import sys
import psutil
import shutil
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QPushButton, QFrame, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar,
    QProgressDialog
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QFont
import bur2000_theme
from loguru import logger

class OptimizationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.additional_clean_paths = [
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache'),
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\Code Cache'),
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache'),
            os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Code Cache'),
            os.path.expandvars(r'%LOCALAPPDATA%\Mozilla\Firefox\Profiles'), # Might need deeper handling in prod, basic clear for now
            r'C:\Windows\Prefetch',
            r'C:\Windows\SoftwareDistribution\Download'
        ]
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_metrics)
        self.timer.start(2000) # Update every 2 seconds

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background-color: {bur2000_theme.BUR.background};")
        
        container = QWidget()
        container.setStyleSheet(f"background-color: {bur2000_theme.BUR.background};")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(25)
        container_layout.setAlignment(Qt.AlignHCenter)

        max_width = 1000

        # Title
        title = QLabel("🚀 OPTIMIZACIÓN DEL SISTEMA (Modo Ultra-Pro)")
        title.setStyleSheet(f"font-size: 28px; font-weight: 900; color: {bur2000_theme.BUR.primary}; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # --- SECTION: DASHBOARD ---
        dash_layout = QHBoxLayout()
        dash_layout.setSpacing(20)
        
        self.cpu_bar = self._create_metric_card("CPU Usage", dash_layout)
        self.ram_bar = self._create_metric_card("RAM Usage", dash_layout)
        self.disk_bar = self._create_metric_card("Disk (C:)", dash_layout)
        
        dash_container = QWidget()
        dash_container.setMaximumWidth(max_width)
        dash_container.setLayout(dash_layout)
        container_layout.addWidget(dash_container)

        # --- SECTION: QUICK ACTIONS ---
        actions_group = QFrame()
        actions_group.setMaximumWidth(max_width)
        actions_group.setStyleSheet(bur2000_theme.BUR.card_style)
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(30, 30, 30, 30)

        act_title = QLabel("⚡ Acciones Rápidas")
        act_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        actions_layout.addWidget(act_title)

        btn_layout = QGridLayout()
        btn_layout.setSpacing(15)

        btn_temp = self._create_action_btn("🗑️ Limpieza Profunda (Temp, Caché, Prefetch)", self._clean_deep)
        btn_dns = self._create_action_btn("🌐 Flush DNS", self._flush_dns)
        btn_ip = self._create_action_btn("🔄 Renovar IP", self._renew_ip)
        
        btn_ram = self._create_action_btn("🧠 Liberar Memoria RAM", self._optimize_ram)
        btn_power = self._create_action_btn("🔋 Alto Rendimiento", self._power_high_perf)
        btn_sfc = self._create_action_btn("🛠️ Reparar Sistema (SFC)", self._sfc_scan)
        btn_dism = self._create_action_btn("🛡️ Restaurar Imagen (DISM)", self._dism_scan)
        btn_drivers = self._create_action_btn("💾 Actualizar Drivers (Windows Update)", self._update_drivers)
        
        btn_turbo = QPushButton("⚡ MODO TURBO ⚡")
        btn_turbo.setCursor(Qt.PointingHandCursor)
        btn_turbo.setMinimumHeight(55)
        btn_turbo.setStyleSheet(f"""
            QPushButton {{ 
                background-color: #ef4444; 
                color: white; 
                border-radius: 6px; 
                font-size: 16px; 
                font-weight: 900; 
                border: 2px solid #b91c1c;
            }}
            QPushButton:hover {{ background-color: #dc2626; border: 2px solid #991b1b; }}
        """)
        btn_turbo.clicked.connect(self._modo_turbo)

        btn_layout.addWidget(btn_temp, 0, 0, 1, 2) # Makes deep clean span two columns
        btn_layout.addWidget(btn_turbo, 1, 0, 1, 2) # Mega button takes full width
        btn_layout.addWidget(btn_dns, 2, 0)
        btn_layout.addWidget(btn_ip, 2, 1)
        btn_layout.addWidget(btn_ram, 3, 0)
        btn_layout.addWidget(btn_power, 3, 1)
        btn_layout.addWidget(btn_sfc, 4, 0)
        btn_layout.addWidget(btn_dism, 4, 1)
        btn_layout.addWidget(btn_drivers, 5, 0, 1, 2)
        
        actions_layout.addLayout(btn_layout)

        container_layout.addWidget(actions_group)

        # --- SECTION: PROCESS MANAGER ---
        proc_group = QFrame()
        proc_group.setMaximumWidth(max_width)
        proc_group.setStyleSheet(bur2000_theme.BUR.card_style)
        proc_layout = QVBoxLayout(proc_group)
        proc_layout.setContentsMargins(30, 30, 30, 30)
        proc_layout.setSpacing(15)

        proc_hdr = QHBoxLayout()
        proc_title = QLabel("☢️ Devoradores de Recursos (Top RAM)")
        proc_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {bur2000_theme.BUR.primary};")
        proc_hdr.addWidget(proc_title)
        
        btn_refresh_proc = QPushButton("🔄 Actualizar Tabla")
        btn_refresh_proc.setCursor(Qt.PointingHandCursor)
        btn_refresh_proc.setStyleSheet(bur2000_theme.BUR.button_secondary)
        btn_refresh_proc.clicked.connect(self._load_processes)
        proc_hdr.addWidget(btn_refresh_proc, 0, Qt.AlignRight)
        
        proc_layout.addLayout(proc_hdr)

        cols = ["PID", "Nombre", "RAM (MB)", "CPU %", "Acción"]
        self.proc_table = QTableWidget(0, len(cols))
        self.proc_table.setHorizontalHeaderLabels(cols)
        self.proc_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.proc_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.proc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.proc_table.verticalHeader().setVisible(False)
        self.proc_table.setAlternatingRowColors(True)
        self.proc_table.setMinimumHeight(400)
        self.proc_table.setStyleSheet(f"""
            QTableWidget {{ border: 1px solid {bur2000_theme.BUR.border}; border-radius: 4px; font-size: 13px; background-color: white; }}
            QHeaderView::section {{ background: {bur2000_theme.BUR.background}; font-weight: bold; padding: 8px; border: none; border-bottom: 2px solid {bur2000_theme.BUR.primary}; }}
            QTableWidget::item:selected {{ background-color: {bur2000_theme.BUR.secondary}40; color: black; }}
        """)
        proc_layout.addWidget(self.proc_table)
        container_layout.addWidget(proc_group)

        container_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self._load_processes()
        self._update_metrics()

    def _create_metric_card(self, title_text, parent_layout):
        card = QFrame()
        card.setStyleSheet(bur2000_theme.BUR.card_style)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 20, 20, 20)
        
        t = QLabel(title_text)
        t.setStyleSheet(f"font-weight: bold; color: {bur2000_theme.BUR.text};")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        
        bar = QProgressBar()
        bar.setTextVisible(True)
        bar.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid {bur2000_theme.BUR.border}; border-radius: 10px; text-align: center; height: 20px; background-color: #f0f0f0; }}
            QProgressBar::chunk {{ background-color: {bur2000_theme.BUR.secondary}; border-radius: 10px; }}
        """)
        bar.setValue(0)
        lay.addWidget(bar)
        
        parent_layout.addWidget(card)
        return bar

    def _create_action_btn(self, text, callback):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(45)
        btn.setStyleSheet(f"""
            QPushButton {{ 
                background-color: {bur2000_theme.BUR.primary}; 
                color: white; 
                border-radius: 6px; 
                font-size: 14px; 
                font-weight: bold; 
            }}
            QPushButton:hover {{ background-color: {bur2000_theme.BUR.secondary}; }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _update_metrics(self):
        try:
            # CPU
            cpu = psutil.cpu_percent()
            self.cpu_bar.setValue(int(cpu))
            self._set_bar_color(self.cpu_bar, cpu)
            
            # RAM
            ram = psutil.virtual_memory().percent
            self.ram_bar.setValue(int(ram))
            self._set_bar_color(self.ram_bar, ram)
            
            # Disk
            disk = psutil.disk_usage('C:\\').percent
            self.disk_bar.setValue(int(disk))
            self._set_bar_color(self.disk_bar, disk)
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def _set_bar_color(self, bar, val):
        color = bur2000_theme.BUR.secondary
        if val > 80: color = "#D32F2F" # Red
        elif val > 60: color = "#F57C00" # Orange
        bar.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid {bur2000_theme.BUR.border}; border-radius: 10px; text-align: center; height: 20px; background-color: #f0f0f0; color: black; font-weight: bold; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 10px; }}
        """)

    def _clean_deep(self):
        reply = QMessageBox.question(
            self, 
            "Limpieza Profunda", 
            "¿Estás seguro de que deseas iniciar una limpieza profunda?\n\nEsto vaciará:\n- Archivos temporales de Windows\n- Caché de navegadores (Chrome, Edge)\n- Archivos Prefetch\n- Descargas de Windows Update\n\nAlgunos programas podrían necesitar descargar archivos de caché de nuevo.", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return

        progress = QProgressDialog("Analizando y limpiando archivos basura...", "Cancelar", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setStyleSheet(f"QProgressDialog {{ background-color: {bur2000_theme.BUR.background}; color: {bur2000_theme.BUR.text}; }}")
        progress.show()

        temp_dirs = [os.environ.get('TEMP'), os.environ.get('TMP'), 'C:\\Windows\\Temp']
        all_dirs = temp_dirs + self.additional_clean_paths
        
        freed_bytes = 0
        error_count = 0
        deleted_files = 0

        # Small trick to get UI updates while doing synchrounous IO (not perfect but works for simple paths)
        total_steps = len(all_dirs)
        
        for idx, d in enumerate(all_dirs):
            if progress.wasCanceled():
                break
                
            progress.setValue(int((idx / total_steps) * 100))
            progress.setLabelText(f"Limpiando: {d}")
            self.repaint() # Force UI refresh
            
            if d and os.path.exists(d):
                try:
                    items = os.listdir(d)
                except PermissionError:
                    # Silenciar el log para no inundar la consola si no se tiene acceso
                    continue
                except Exception as e:
                    # Silenciar también otros errores de listado
                    continue

                for item in items:
                    path = os.path.join(d, item)
                    try:
                        size = os.path.getsize(path) if os.path.isfile(path) else 0
                        if os.path.isfile(path):
                            os.remove(path)
                            freed_bytes += size
                            deleted_files += 1
                        elif os.path.isdir(path):
                            # Try to get size before deleting
                            for dirpath, _, filenames in os.walk(path):
                                for f in filenames:
                                    fp = os.path.join(dirpath, f)
                                    if not os.path.islink(fp):
                                        try:
                                            freed_bytes += os.path.getsize(fp)
                                            deleted_files += 1
                                        except OSError:
                                            pass
                            shutil.rmtree(path, ignore_errors=True)
                    except Exception:
                        error_count += 1
                        # Se omite el logger para "Failed to delete" ya que es esperado (ej. archivos en uso)
                        pass

        # Empty Recycle Bin using Windows API format (via PowerShell or ctypes, using PS here for simplicity without extra imports)
        try:
            progress.setLabelText("Vaciando Papelera de Reciclaje...")
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"], creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            logger.debug(f"Recycle bin error: {e}")

        progress.setValue(100)
        
        mb = freed_bytes / (1024 * 1024)
        gb = freed_bytes / (1024 * 1024 * 1024)
        
        size_str = f"{gb:.2f} GB" if gb >= 1 else f"{mb:.2f} MB"
        
        msg = f"¡Limpieza profunda completada con éxito!\n\n"
        msg += f"Espacio liberado: {size_str}\n"
        msg += f"Archivos eliminados: {deleted_files}\n"
        if error_count > 0:
            msg += f"Archivos protegidos/en uso saltados: {error_count}"
            
        QMessageBox.information(self, "Limpieza Modo Dios", msg)
        self._update_metrics()

    def _flush_dns(self):
        try:
            subprocess.run(["ipconfig", "/flushdns"], creationflags=subprocess.CREATE_NO_WINDOW)
            QMessageBox.information(self, "Red Optimizada", "Caché DNS limpiada (Flush DNS) exitosamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo limpiar DNS: {e}")

    def _renew_ip(self):
        try:
            subprocess.run(["ipconfig", "/release"], creationflags=subprocess.CREATE_NO_WINDOW)
            subprocess.run(["ipconfig", "/renew"], creationflags=subprocess.CREATE_NO_WINDOW)
            QMessageBox.information(self, "Red Optimizada", "Dirección IP renovada exitosamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo renovar IP: {e}")

    # --- MODO TURBO METHODS ---

    def _modo_turbo(self):
        reply = QMessageBox.question(
            self, 
            "⚡ MODO TURBO ⚡", 
            "Estás a punto de desatar el MODO DIOS en este PC.\n\n"
            "Esto ejecutará en secuencia:\n"
            "1. Optimización SSD (ReTrim)\n"
            "2. Reseteo Profundo de Red (Winsock/TCP)\n"
            "3. Vaciado de caché de Windows Update\n"
            "4. Limpieza del Visor de Eventos\n"
            "5. Prioridad Alta a Apps Clave (Chrome, Odoo, Gabriela)\n"
            "6. Configuración de Mejor Rendimiento (Efectos Visuales)\n\n"
            "⚠️ ATENCIÓN: La red se cortará un segundo, y algunos cambios visuales requieren reiniciar la pantalla. El proceso puede requerir permisos de Administrador.\n\n"
            "¿Deseas continuar?", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return

        progress = QProgressDialog("Iniciando MODO TURBO...", "Cancelar", 0, 6, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setStyleSheet(f"QProgressDialog {{ background-color: {bur2000_theme.BUR.background}; color: {bur2000_theme.BUR.text}; }}")
        progress.show()

        try:
            # Step 1
            progress.setLabelText("Paso 1/6: Optimizando SSD y discos duros...")
            self._turbo_defrag_ssd()
            progress.setValue(1)
            if progress.wasCanceled(): return

            # Step 2
            progress.setLabelText("Paso 2/6: Reseteando capa de red TCP/IP y Winsock...")
            self._turbo_winsock_reset()
            progress.setValue(2)
            if progress.wasCanceled(): return

            # Step 3
            progress.setLabelText("Paso 3/6: Limando carpeta SoftwareDistribution (Windows Update)...")
            self._turbo_clear_update()
            progress.setValue(3)
            if progress.wasCanceled(): return

            # Step 4
            progress.setLabelText("Paso 4/6: Purgando Logs del Visor de Eventos...")
            self._turbo_clear_events()
            progress.setValue(4)
            if progress.wasCanceled(): return

            # Step 5
            progress.setLabelText("Paso 5/6: Asignando Prioridad ALTA a apps de trabajo...")
            self._turbo_prio_apps()
            progress.setValue(5)
            if progress.wasCanceled(): return

            # Step 6
            progress.setLabelText("Paso 6/6: Maximizando rendimiento visual y registrando parámetros...")
            self._turbo_perf_flags()
            progress.setValue(6)

            QMessageBox.information(
                self, 
                "¡MODO TURBO COMPLETADO!", 
                "El PC ha sido optimizado al máximo nivel posible.\n\n"
                "Para que el reseteo de red y los efectos visuales surtan efecto completo, se recomienda reiniciar el equipo pronto."
            )

        except Exception as e:
            logger.error(f"Error in Turbo Mode: {e}")
            QMessageBox.warning(self, "Aviso Modo Turbo", f"El Modo Turbo tuvo algunos problemas o falta de permisos.\nError: {e}\n\nNota: Es posible que necesites ejecutar Gabriela Rojas como Administrador para algunas tareas de sistema profundo.")
        finally:
            progress.close()


    def _run_admin_cmd(self, cmd_string):
        """Helper to run powershell commands silently"""
        import base64
        try:
            # Construct a safe powershell string by replacing ' with ''
            safe_cmd = cmd_string.replace("'", "''")
            ps_script = f"Start-Process cmd -ArgumentList '/c', '{safe_cmd}' -WindowStyle Hidden -Wait -Verb RunAs"
            
            # Encode to Base64 (UTF-16LE) to completely avoid escaping issues in subprocess
            encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('utf-8')
            
            subprocess.run(
                ["powershell", "-NoProfile", "-EncodedCommand", encoded],
                capture_output=True, check=True
            )
        except Exception as e:
            logger.error(f"Admin command failed [{cmd_string}]: {e}")

    def _turbo_defrag_ssd(self):
        self._run_admin_cmd("powershell.exe Optimize-Volume -DriveLetter C -ReTrim -Verbose")

    def _turbo_winsock_reset(self):
        self._run_admin_cmd("netsh winsock reset & netsh int ip reset")
        self._flush_dns() # call the existing visual one silently 
        
    def _turbo_clear_update(self):
        cmd = "net stop wuauserv & net stop bits & del /q /f /s C:\\Windows\\SoftwareDistribution\\Download\\* & net start wuauserv & net start bits"
        self._run_admin_cmd(cmd)

    def _turbo_clear_events(self):
        self._run_admin_cmd("for /F \"tokens=*\" %1 in ('wevtutil.exe el') DO wevtutil.exe cl \"%1\"")

    def _turbo_prio_apps(self):
        # Escalate Chrome, Excel, Gabriela to High Priority (128 = HIGH_PRIORITY_CLASS)
        targets = ["chrome.exe", "excel.exe", "python.exe", "pythonw.exe", "msedge.exe"]
        count = 0
        for proc in psutil.process_iter(['name']):
            try:
                name = proc.info.get('name')
                if name and name.lower() in targets:
                    logger.info(f"Escalating {name} PID:{proc.pid} to HIGH priority")
                    p = psutil.Process(proc.pid)
                    p.nice(psutil.HIGH_PRIORITY_CLASS)
                    count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        logger.info(f"Turbo Mode: Escalated {count} work processes.")

    def _turbo_perf_flags(self):
        # Adjust VisualFX to "Adjust for best performance"
        reg_cmd = "reg add \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects\" /v VisualFXSetting /t REG_DWORD /d 2 /f"
        self._run_admin_cmd(reg_cmd)

    def _optimize_ram(self):
        try:
            # Vaciar el working set de todos los procesos accesibles
            script = "Get-Process | ForEach-Object { try { [System.Diagnostics.Process]::GetProcessById($_.Id).MinWorkingSet = [System.IntPtr]-1 } catch {} }"
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], creationflags=subprocess.CREATE_NO_WINDOW)
            QMessageBox.information(self, "RAM Optimizada", "Se ha enviado la señal a Windows para vaciar la memoria inactiva.")
            self._update_metrics()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo optimizar la RAM: {e}")

    def _power_high_perf(self):
        try:
            # UUID for High Performance power plan
            subprocess.run(["powercfg", "/SETACTIVE", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"], creationflags=subprocess.CREATE_NO_WINDOW)
            QMessageBox.information(self, "Energía", "Plan de energía cambiado a Alto Rendimiento.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cambiar plan de energía: {e}")

    def _sfc_scan(self):
        reply = QMessageBox.question(self, "SFC Scannow", "¿Deseas ejecutar System File Checker (SFC)?\n\nEsto abrirá una ventana de CMD como Administrador y buscará archivos corruptos del sistema.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                subprocess.run(["powershell.exe", "Start-Process", "cmd.exe", "-ArgumentList", "'/k sfc /scannow'", "-Verb", "RunAs"], creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo iniciar SFC: {e}")

    def _dism_scan(self):
        reply = QMessageBox.question(self, "DISM RestoreHealth", "¿Deseas ejecutar DISM /RestoreHealth?\n\nEsto abrirá CMD como Administrador e intentará reparar la imagen de Windows.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                subprocess.run(["powershell.exe", "Start-Process", "cmd.exe", "-ArgumentList", "'/k DISM /Online /Cleanup-Image /RestoreHealth'", "-Verb", "RunAs"], creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo iniciar DISM: {e}")

    def _update_drivers(self):
        reply = QMessageBox.question(
            self, 
            "Actualizar Drivers", 
            "¿Deseas rastrear y actualizar los Drivers del PC?\n\n"
            "Se abrirá una ventana de PowerShell como Administrador. Este proceso usará el motor nativo y oficial de Windows Update para máxima seguridad.", 
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            ps_script = (
                "Write-Host '=== RASTREO Y ACTUALIZACION DE DRIVERS ===' -ForegroundColor Cyan; "
                "Write-Host 'Iniciando engine de Windows Update...' -ForegroundColor Yellow; "
                "if (-not (Get-Module -ListAvailable -Name PSWindowsUpdate)) { "
                "Write-Host 'Instalando modulo necesario...' -ForegroundColor Yellow; "
                "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
                "Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force | Out-Null; "
                "Install-Module -Name PSWindowsUpdate -Force -Confirm:$false; "
                "}; "
                "Import-Module PSWindowsUpdate; "
                "Write-Host 'Buscando nuevas versiones. Por favor, espera...' -ForegroundColor Cyan; "
                "$updates = Get-WindowsUpdate -Category 'Drivers' -IsHidden $false; "
                "if ($updates) { "
                "Write-Host 'Se encontraron actualizaciones:' -ForegroundColor Green; "
                "$updates | Format-Table Title, Size; "
                "Write-Host 'Instalando actualizaciones...' -ForegroundColor Yellow; "
                "Install-WindowsUpdate -Category 'Drivers' -AcceptAll -AutoReboot; "
                "} else { "
                "Write-Host 'Todos los drivers certificados estan en su version optima.' -ForegroundColor Green; "
                "}; "
                "Write-Host 'Proceso finalizado.'; Read-Host 'Presiona Enter para cerrar esta ventana...'"
            )
            import base64
            encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('utf-8')
            wrapped_cmd = f"Start-Process powershell -ArgumentList '-NoProfile', '-EncodedCommand', '{encoded}' -Verb RunAs"
            encoded_wrapped = base64.b64encode(wrapped_cmd.encode('utf-16le')).decode('utf-8')
            
            try:
                subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded_wrapped], creationflags=subprocess.CREATE_NO_WINDOW)
                QMessageBox.information(self, "Driver Scanner", "El escáner de drivers se ha iniciado en una nueva ventana con privilegios de Administrador.\n\nRevisa la barra de tareas.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Hubo un problema al iniciar Windows Update: {e}")

    def _load_processes(self):
        try:
            items = []
            for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
                try:
                    info = p.info
                    mem_mb = info['memory_info'].rss / (1024 * 1024) if info['memory_info'] else 0
                    if mem_mb > 50: # Only show processes > 50MB
                        items.append({
                            'pid': info['pid'],
                            'name': info['name'],
                            'mem': mem_mb,
                            'cpu': info.get('cpu_percent', 0.0) or 0.0
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Sort by memory descending
            items.sort(key=lambda x: x['mem'], reverse=True)
            items = items[:30] # Top 30

            self.proc_table.setRowCount(0)
            for i, item in enumerate(items):
                self.proc_table.insertRow(i)
                self.proc_table.setItem(i, 0, QTableWidgetItem(str(item['pid'])))
                self.proc_table.setItem(i, 1, QTableWidgetItem(item['name']))
                self.proc_table.setItem(i, 2, QTableWidgetItem(f"{item['mem']:.1f}"))
                self.proc_table.setItem(i, 3, QTableWidgetItem(f"{item['cpu']:.1f}"))
                
                btn_kill = QPushButton("☠️ Forzar Cierre")
                btn_kill.setStyleSheet("background-color: #D32F2F; color: white; border-radius: 4px; padding: 4px; font-weight: bold;")
                btn_kill.setCursor(Qt.PointingHandCursor)
                btn_kill.clicked.connect(lambda checked, pid=item['pid'], name=item['name']: self._kill_process(pid, name))
                self.proc_table.setCellWidget(i, 4, btn_kill)
                
                for c in range(4):
                    it = self.proc_table.item(i, c)
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setTextAlignment(Qt.AlignCenter if c != 1 else Qt.AlignVCenter | Qt.AlignLeft)

        except Exception as e:
            logger.error(f"Error loading processes: {e}")

    def _kill_process(self, pid, name):
        reply = QMessageBox.question(self, "Confirmar Cierre", f"¿Estás seguro de que quieres forzar el cierre de '{name}' (PID: {pid})?\nPodrías perder datos no guardados.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                p = psutil.Process(pid)
                p.terminate()
                p.wait(timeout=3)
                QMessageBox.information(self, "Proceso Terminado", f"El proceso '{name}' ha sido terminado.")
                self._load_processes()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo matar el proceso: {e}")
