import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import os
from pathlib import Path
from datetime import datetime
import threading
from dataclasses import dataclass, field
from typing import Dict, List
import logging
from enum import Enum

# ==================== ENUMS Y DATACLASSES ====================

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

@dataclass
class LogEntry:
    timestamp: str
    level: LogLevel
    message: str
    
    def __str__(self):
        return f"[{self.timestamp}] [{self.level.value}] {self.message}"

@dataclass
class LogStatistics:
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    debug_count: int = 0
    processed_recordings: int = 0
    failed_recordings: int = 0
    total_tokens_used: int = 0
    
    def to_dict(self):
        return {
            'errores': self.error_count,
            'advertencias': self.warning_count,
            'info': self.info_count,
            'debug': self.debug_count,
            'grabaciones_procesadas': self.processed_recordings,
            'grabaciones_fallidas': self.failed_recordings,
            'tokens_usados': self.total_tokens_used
        }

# ==================== LOG MANAGER ====================

class LogManager:
    def __init__(self, log_directory: str):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        self.logs: List[LogEntry] = []
        self.stats = LogStatistics()
        self.log_file = self.log_directory / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
    def add_log(self, level: LogLevel, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = LogEntry(timestamp, level, message)
        self.logs.append(entry)
        
        # Actualizar estadísticas
        if level == LogLevel.ERROR:
            self.stats.error_count += 1
        elif level == LogLevel.WARNING:
            self.stats.warning_count += 1
        elif level == LogLevel.INFO:
            self.stats.info_count += 1
        elif level == LogLevel.DEBUG:
            self.stats.debug_count += 1
        
        # Guardar en archivo
        self._write_to_file(entry)
        
        return entry
    
    def add_debug(self, message: str):
        return self.add_log(LogLevel.DEBUG, message)
    
    def add_info(self, message: str):
        return self.add_log(LogLevel.INFO, message)
    
    def add_warning(self, message: str):
        return self.add_log(LogLevel.WARNING, message)
    
    def add_error(self, message: str):
        return self.add_log(LogLevel.ERROR, message)
    
    def add_processed_recording(self, filename: str):
        self.stats.processed_recordings += 1
        self.add_info(f"Grabación procesada: {filename}")
    
    def add_failed_recording(self, filename: str, error: str):
        self.stats.failed_recordings += 1
        self.add_error(f"Grabación fallida: {filename} - {error}")
    
    def _write_to_file(self, entry: LogEntry):
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(str(entry) + '\n')
        except Exception as e:
            print(f"Error escribiendo log: {e}")
    
    def get_logs_by_level(self, level: LogLevel) -> List[LogEntry]:
        return [log for log in self.logs if log.level == level]
    
    def get_all_logs_text(self) -> str:
        return '\n'.join(str(log) for log in self.logs)
    
    def export_stats(self, filepath: str):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.stats.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.add_error(f"Error exportando estadísticas: {e}")

# ==================== CONFIG LOADER ====================

class ConfigLoader:
    def __init__(self):
        self.config: Dict = {}
        self.config_path: str = ""
        
    def load_config(self, filepath: str) -> bool:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.config_path = filepath
            return True
        except Exception as e:
            raise Exception(f"Error cargando configuración: {e}")
    
    def get_config(self) -> Dict:
        return self.config
    
    def get_value(self, *keys, default=None):
        """Obtener valor anidado usando notación de puntos: get_value('mongo_db', 'host')"""
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def get_config_text(self) -> str:
        return json.dumps(self.config, indent=2, ensure_ascii=False)

# ==================== GUI PRINCIPAL ====================

class AudioAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Analyzer - Control Panel")
        self.root.geometry("1400x900")
        self.root.resizable(True, True)
        
        # Managers
        self.config_loader = ConfigLoader()
        self.log_manager = None
        
        # Variables de control
        self.processing = False
        self.current_log_filter = LogLevel.DEBUG
        
        # Estilo
        self.setup_styles()
        
        # UI
        self.setup_ui()
        
    def setup_styles(self):
        """Configurar estilos de ttk"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores personalizados
        style.configure('Header.TLabel', font=('Arial', 14, 'bold'), foreground='#1a73e8')
        style.configure('Success.TLabel', foreground='#188038')
        style.configure('Error.TLabel', foreground='#d33b27')
        style.configure('Warning.TLabel', foreground='#f9ab00')
        style.configure('Info.TLabel', foreground='#1a73e8')
        
    def setup_ui(self):
        """Crear interfaz principal"""
        # Frame principal con notebook (pestañas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Pestaña 1: Configuración
        self.create_config_tab()
        
        # Pestaña 2: Logs
        self.create_logs_tab()
        
        # Pestaña 3: Estadísticas
        self.create_stats_tab()
        
        # Pestaña 4: Monitor en Tiempo Real
        self.create_monitor_tab()
        
        # Barra de estado
        self.setup_status_bar()
        
    def create_config_tab(self):
        """Pestaña de carga y visualización de configuración"""
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="Configuración")
        
        # Frame superior: Botones de control
        btn_frame = ttk.Frame(config_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Cargar Config (JSON)", 
                  command=self.load_config_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Recargar", 
                  command=self.reload_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Guardar Como...", 
                  command=self.save_config).pack(side=tk.LEFT, padx=5)
        
        self.config_status_label = ttk.Label(btn_frame, text="Sin configuración cargada",
                                             style='Error.TLabel')
        self.config_status_label.pack(side=tk.RIGHT, padx=5)
        
        # Frame con texto de configuración
        text_frame = ttk.LabelFrame(config_frame, text="Contenido del JSON", padding=10)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.config_text = scrolledtext.ScrolledText(text_frame, height=25, 
                                                     yscrollcommand=scrollbar.set,
                                                     font=('Courier', 10))
        self.config_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.config_text.yview)
        
        # Frame con tabla de valores clave
        info_frame = ttk.LabelFrame(config_frame, text="Configuracion Detectada", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Crear tabla
        columns = ('Parámetro', 'Valor')
        self.config_tree = ttk.Treeview(info_frame, columns=columns, height=8, show='headings')
        self.config_tree.column('Parámetro', width=100)
        self.config_tree.column('Valor', width=600)
        self.config_tree.heading('Parámetro', text='Parámetro')
        self.config_tree.heading('Valor', text='Valor')
        self.config_tree.pack(fill=tk.BOTH, expand=True)
        
        scrollbar2 = ttk.Scrollbar(info_frame, orient=tk.VERTICAL, command=self.config_tree.yview)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        self.config_tree.configure(yscrollcommand=scrollbar2.set)
        
    def create_logs_tab(self):
        """Pestaña de visualización de logs"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="Logs")
        
        # Frame de filtros
        filter_frame = ttk.Frame(logs_frame)
        filter_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(filter_frame, text="Filtrar por nivel:").pack(side=tk.LEFT, padx=5)
        
        self.filter_var = tk.StringVar(value="DEBUG")
        for level in LogLevel:
            ttk.Radiobutton(filter_frame, text=level.value, variable=self.filter_var,
                          value=level.value, 
                          command=self.update_logs_display).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(filter_frame, text="Mostrar Todo", 
                  command=lambda: self.show_all_logs()).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Limpiar", 
                  command=self.clear_logs_display).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Exportar Logs", 
                  command=self.export_logs).pack(side=tk.RIGHT, padx=5)
        
        # Text widget para logs
        text_frame = ttk.LabelFrame(logs_frame, text="Registro de Eventos", padding=10)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.logs_text = scrolledtext.ScrolledText(text_frame, height=30,
                                                   yscrollcommand=scrollbar.set,
                                                   font=('Courier', 9),
                                                   wrap=tk.WORD)
        self.logs_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.logs_text.yview)
        
        # Configurar tags para colores
        self.logs_text.tag_config('ERROR', foreground='#d33b27', background='#fce5e0')
        self.logs_text.tag_config('WARNING', foreground='#f9ab00', background='#fff3e0')
        self.logs_text.tag_config('INFO', foreground='#1a73e8')
        self.logs_text.tag_config('DEBUG', foreground='#5f6368')
        
    def create_stats_tab(self):
        """Pestaña de estadísticas"""
        stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(stats_frame, text="Estadísticas")
        
        # Frame de botones
        btn_frame = ttk.Frame(stats_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Actualizar", 
                  command=self.refresh_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Exportar Estadísticas", 
                  command=self.export_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Resetear Contadores", 
                  command=self.reset_stats).pack(side=tk.LEFT, padx=5)
        
        # Frame principal con grid de estadísticas
        main_stats_frame = ttk.Frame(stats_frame)
        main_stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Crear 2 columnas
        left_frame = ttk.LabelFrame(main_stats_frame, text="Logs", padding=20)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        right_frame = ttk.LabelFrame(main_stats_frame, text="Procesamiento", padding=20)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        # Estadísticas de logs (lado izquierdo)
        self.create_stat_widget(left_frame, "🔴 Errores", "errors", 0)
        self.create_stat_widget(left_frame, "⚠️ Advertencias", "warnings", 0)
        self.create_stat_widget(left_frame, "ℹ️ Información", "info", 0)
        self.create_stat_widget(left_frame, "🔧 Debug", "debug", 0)
        
        # Estadísticas de procesamiento (lado derecho)
        self.create_stat_widget(right_frame, "✅ Grabaciones Procesadas", "processed", 0)
        self.create_stat_widget(right_frame, "❌ Grabaciones Fallidas", "failed", 0)
        self.create_stat_widget(right_frame, "💾 Tokens Usados", "tokens", 0)
        
        # Bottom info
        info_frame = ttk.LabelFrame(stats_frame, text="Información de Sesión", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.session_info_text = scrolledtext.ScrolledText(info_frame, height=5, font=('Courier', 9))
        self.session_info_text.pack(fill=tk.BOTH, expand=True)
        
    def create_monitor_tab(self):
        """Pestaña de monitoreo en tiempo real"""
        monitor_frame = ttk.Frame(self.notebook)
        self.notebook.add(monitor_frame, text="Monitor en Tiempo Real")
        
        # Frame de control
        ctrl_frame = ttk.Frame(monitor_frame)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # self.monitor_start_btn = ttk.Button(ctrl_frame, text="Iniciar Monitoreo",
        #                                    command=self.start_monitoring)
        # self.monitor_start_btn.pack(side=tk.LEFT, padx=5)
        
        # self.monitor_stop_btn = ttk.Button(ctrl_frame, text="Detener Monitoreo",
        #                                   command=self.stop_monitoring, state=tk.DISABLED)
        # self.monitor_stop_btn.pack(side=tk.LEFT, padx=5)
        
        # ttk.Button(ctrl_frame, text="Simular Evento",
        #           command=self.simulate_event).pack(side=tk.LEFT, padx=5)
        
        self.monitor_status = ttk.Label(ctrl_frame, text="Detenido", style='Error.TLabel')
        self.monitor_status.pack(side=tk.RIGHT, padx=5)
        
        # Monitor text
        monitor_text_frame = ttk.LabelFrame(monitor_frame, text="Eventos en Vivo", padding=10)
        monitor_text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(monitor_text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.monitor_text = scrolledtext.ScrolledText(monitor_text_frame, height=30,
                                                      yscrollcommand=scrollbar.set,
                                                      font=('Courier', 9))
        self.monitor_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.monitor_text.yview)
        
        self.monitor_text.tag_config('LIVE', foreground='#188038', background='#e6f4ea')
    
    def create_stat_widget(self, parent, label, key, initial_value):
        """Helper para crear widgets de estadísticas"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=15)
        
        ttk.Label(frame, text=label, font=('Arial', 11, 'bold')).pack(anchor=tk.W)
        
        value_label = ttk.Label(frame, text=str(initial_value), 
                               font=('Arial', 24, 'bold'), foreground='#1a73e8')
        value_label.pack(anchor=tk.W)
        
        # Guardar referencia
        if not hasattr(self, 'stat_labels'):
            self.stat_labels = {}
        self.stat_labels[key] = value_label
    
    def setup_status_bar(self):
        """Barra de estado en la parte inferior"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Listo", relief=tk.SUNKEN)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.time_label = ttk.Label(status_frame, text=self.get_current_time())
        self.time_label.pack(side=tk.RIGHT, padx=10)
        
        # Actualizar hora
        self.update_time()
    
    def update_time(self):
        """Actualizar hora en barra de estado"""
        self.time_label.config(text=self.get_current_time())
        self.root.after(1000, self.update_time)
    
    def get_current_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # ==================== MÉTODOS DE CONFIGURACIÓN ====================
    
    def load_config_file(self):
        """Cargar archivo de configuración"""
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo de configuración",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                self.config_loader.load_config(filepath)
                self.initialize_log_manager()
                self.display_config()
                self.config_status_label.config(
                    text=f"✓ Configurado: {Path(filepath).name}",
                    style='Success.TLabel'
                )
                self.log_manager.add_info(f"Configuración cargada: {filepath}")
                self.update_status(f"Configuración cargada desde: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo cargar la configuración:\n{e}")
                self.config_status_label.config(text=f"✗ Error", style='Error.TLabel')
    
    def initialize_log_manager(self):
        """Inicializar el gestor de logs basado en config"""
        log_path = self.config_loader.get_value('log', 'path', 
                                               default='./logs')
        self.log_manager = LogManager(log_path)
        self.log_manager.add_info("Sistema inicializado")
    
    def reload_config(self):
        """Recargar configuración actual"""
        if self.config_loader.config_path:
            try:
                self.config_loader.load_config(self.config_loader.config_path)
                self.display_config()
                self.log_manager.add_info("Configuración recargada")
                self.update_status("Configuración recargada")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo recargar:\n{e}")
        else:
            messagebox.showwarning("Advertencia", "Primero carga una configuración")
    
    def save_config(self):
        """Guardar configuración actual"""
        if not self.config_loader.config:
            messagebox.showwarning("Advertencia", "No hay configuración cargada")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.config_loader.config, f, indent=2, ensure_ascii=False)
                self.log_manager.add_info(f"Configuración guardada: {filepath}")
                self.update_status(f"Guardado en: {filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar:\n{e}")
    
    def display_config(self):
        """Mostrar configuración en la UI"""
        self.config_text.delete(1.0, tk.END)
        self.config_text.insert(1.0, self.config_loader.get_config_text())
        
        # Llenar tabla de la config detectada
        self.config_tree.delete(*self.config_tree.get_children())
        
        key_values = [
            ('AI Provider', self.config_loader.get_value('ai_provider', default='N/A')),
            ('STT Provider', self.config_loader.get_value('stt_provider', default='N/A')),
            ('Claude Model', self.config_loader.get_value('claude', 'model', default='N/A')),
            ('Source Type', 'folder' if self.config_loader.get_value('source', 'folder') else 'another'),
            ('Language', self.config_loader.get_value('transcription_output', 'language', default='N/A')),
            ('Log Level', self.config_loader.get_value('log', 'level', default='N/A')),
            ('Token Limit', self.config_loader.get_value('token_limits', 'monthly_limit', default='N/A')),
            ('Transcription Enabled', self.config_loader.get_value('processing_features', 'transcription_enabled', default='N/A')),
            ('Analysis Enabled', self.config_loader.get_value('processing_features', 'analysis_enabled', default='N/A')),
            ('Sentiment Enabled', self.config_loader.get_value('processing_features', 'sentiment_enabled', default='N/A')),
        ]
        
        for param, value in key_values:
            self.config_tree.insert('', tk.END, values=(param, str(value)))
    
    # ==================== MÉTODOS DE LOGS ====================
    
    def update_logs_display(self):
        """Actualizar display de logs filtrados"""
        if not self.log_manager:
            return
        
        level_str = self.filter_var.get()
        level = LogLevel[level_str]
        
        logs = self.log_manager.get_logs_by_level(level)
        
        self.logs_text.delete(1.0, tk.END)
        for log in logs:
            self.logs_text.insert(tk.END, str(log) + '\n', level_str)
    
    def show_all_logs(self):
        """Mostrar todos los logs"""
        if not self.log_manager:
            return
        
        self.logs_text.delete(1.0, tk.END)
        for log in self.log_manager.logs:
            self.logs_text.insert(tk.END, str(log) + '\n', log.level.value)
    
    def clear_logs_display(self):
        """Limpiar display de logs"""
        self.logs_text.delete(1.0, tk.END)
    
    def export_logs(self):
        """Exportar logs a archivo"""
        if not self.log_manager:
            messagebox.showwarning("Advertencia", "No hay logs para exportar")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(self.log_manager.get_all_logs_text())
                messagebox.showinfo("Éxito", f"Logs exportados a:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo exportar:\n{e}")
    
    # ==================== MÉTODOS DE ESTADÍSTICAS ====================
    
    def refresh_stats(self):
        """Actualizar display de estadísticas"""
        if not self.log_manager:
            return
        
        stats = self.log_manager.stats
        
        # Actualizar etiquetas
        self.stat_labels['errors'].config(text=str(stats.error_count))
        self.stat_labels['warnings'].config(text=str(stats.warning_count))
        self.stat_labels['info'].config(text=str(stats.info_count))
        self.stat_labels['debug'].config(text=str(stats.debug_count))
        self.stat_labels['processed'].config(text=str(stats.processed_recordings))
        self.stat_labels['failed'].config(text=str(stats.failed_recordings))
        self.stat_labels['tokens'].config(text=str(stats.total_tokens_used))
        
        # Información de sesión
        self.session_info_text.delete(1.0, tk.END)
        info = f"""
Tiempo de sesión: {self.get_current_time()}
Total de eventos registrados: {len(self.log_manager.logs)}
Archivo de log: {self.log_manager.log_file}
Directorio de logs: {self.log_manager.log_directory}

Resumen:
  • Errores: {stats.error_count}
  • Advertencias: {stats.warning_count}
  • Información: {stats.info_count}
  • Debug: {stats.debug_count}
  • Grabaciones procesadas: {stats.processed_recordings}
  • Grabaciones fallidas: {stats.failed_recordings}
        """
        self.session_info_text.insert(1.0, info)
    
    def export_stats(self):
        """Exportar estadísticas a JSON"""
        if not self.log_manager:
            messagebox.showwarning("Advertencia", "No hay estadísticas para exportar")
            return
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filepath:
            self.log_manager.export_stats(filepath)
            messagebox.showinfo("Éxito", f"Estadísticas exportadas a:\n{filepath}")
    
    def reset_stats(self):
        """Resetear contadores de estadísticas"""
        if messagebox.askyesno("Confirmar", "¿Resetear todos los contadores?"):
            if self.log_manager:
                self.log_manager.stats = LogStatistics()
                self.log_manager.add_warning("Contadores resetados")
                self.refresh_stats()
    
    # ==================== MÉTODOS DE MONITOREO ====================
    
    def start_monitoring(self):
        """Iniciar monitoreo en tiempo real"""
        self.processing = True
        self.monitor_start_btn.config(state=tk.DISABLED)
        self.monitor_stop_btn.config(state=tk.NORMAL)
        self.monitor_status.config(text="Activo 🟢", style='Success.TLabel')
        self.log_manager.add_info("Monitoreo iniciado")
        self.update_status("Monitoreo EN VIVO")
    
    def stop_monitoring(self):
        """Detener monitoreo"""
        self.processing = False
        self.monitor_start_btn.config(state=tk.NORMAL)
        self.monitor_stop_btn.config(state=tk.DISABLED)
        self.monitor_status.config(text="Detenido 🔴", style='Error.TLabel')
        self.log_manager.add_info("Monitoreo detenido")
        self.update_status("Monitoreo detenido")
    
    def simulate_event(self):
        """Simular evento de procesamiento"""
        if not self.log_manager:
            messagebox.showwarning("Advertencia", "Carga una configuración primero")
            return
        
        import random
        
        events = [
            ("grabacion_001.wav", "procesada", None),
            ("grabacion_002.wav", "fallida", "Error de conexión"),
            ("grabacion_003.wav", "procesada", None),
            ("grabacion_004.wav", "fallida", "Archivo corrupto"),
        ]
        
        filename, status, error = random.choice(events)
        
        if status == "procesada":
            self.log_manager.add_processed_recording(filename)
            msg = f"[PROCESADA] {filename}"
        else:
            self.log_manager.add_failed_recording(filename, error)
            msg = f"[FALLIDA] {filename} - {error}"
        
        # Mostrar en monitor
        if self.processing:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.monitor_text.insert(tk.END, f"[{timestamp}] {msg}\n", 'LIVE')
            self.monitor_text.see(tk.END)
    
    def update_status(self, message):
        """Actualizar barra de estado"""
        self.status_label.config(text=message)

# ==================== MAIN ====================

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioAnalyzerGUI(root)
    root.mainloop()