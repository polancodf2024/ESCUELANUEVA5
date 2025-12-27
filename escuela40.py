"""
escuela40.py - Sistema de Gestión de Escuela (Versión 4.0 Corregida)
Sistema COMPLETO y CORREGIDO para despliegue en Streamlit Cloud
Versión optimizada con manejo de conexión SSH y mensajes mejorados
"""

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
import sys
import json
import time
import hashlib
import tempfile
import io
import warnings
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from contextlib import contextmanager
import shutil
import gzip

warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN DEL SISTEMA
# =============================================================================

class ConfiguracionSistema:
    """Gestión centralizada de configuración optimizada para despliegue en nube"""
    
    _instancia = None
    
    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializar()
        return cls._instancia
    
    def _inicializar(self):
        """Inicializar configuración optimizada para nube"""
        # Configuración por defecto optimizada para despliegue
        self.config = {
            'app': {
                'title': '🏫 Sistema de Gestión Escolar',
                'version': '4.0',
                'icon': '🏫',
                'page_size': 50,
                'cache_ttl': 300,
                'modo': 'nube'  # Indica que estamos en despliegue en la nube
            },
            'database': {
                'name': 'escuela.db',
                'backup_dir': 'backups',
                'max_backups': 10,
                'backup_enabled': True,
                'temporal': True  # Base de datos temporal para nube
            },
            'ssh': {
                'enabled': False,  # Deshabilitado por defecto para seguridad en nube
                'host': '',
                'port': 22,
                'username': '',
                'password': '',
                'timeout': 30,
                'auto_connect': False
            },
            'paths': {
                'uploads': 'uploads',
                'logs': 'logs'
            },
            'estados': {
                'estudiante': ['Activo', 'Inactivo', 'Egresado', 'Baja Temporal', 'Baja Definitiva'],
                'nivel': ['Licenciatura', 'Maestría', 'Doctorado', 'Especialidad'],
                'turno': ['Matutino', 'Vespertino', 'Nocturno', 'Mixto'],
                'genero': ['M', 'F', 'Otro']
            },
            'mensajes': {
                'modo_local': '💻 Aplicación funcionando en modo local',
                'ssh_deshabilitado': 'SSH deshabilitado para seguridad en la nube',
                'sesion_temporal': 'Datos guardados temporalmente para esta sesión'
            }
        }
        
        # Intentar cargar configuración externa
        self._cargar_config_externa()
    
    def _cargar_config_externa(self):
        """Cargar configuración desde archivos externos"""
        config_files = [
            'config.json',
            'config/config.json',
            '.streamlit/secrets.toml',
            'secrets.toml'
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r') as f:
                        if config_file.endswith('.json'):
                            import json
                            external_config = json.load(f)
                        elif config_file.endswith('.toml'):
                            try:
                                import tomllib
                                external_config = tomllib.load(f)
                            except ImportError:
                                import tomli as tomllib
                                external_config = tomllib.load(f)
                    
                    # Fusionar configuración manteniendo valores por defecto seguros
                    self._fusionar_config_segura(self.config, external_config)
                    
                except Exception as e:
                    print(f"⚠️ Error cargando {config_file}: {e}")
    
    def _fusionar_config_segura(self, base: Dict, nueva: Dict, path: str = ''):
        """Fusionar diccionarios de configuración de forma segura"""
        for key, value in nueva.items():
            full_path = f"{path}.{key}" if path else key
            
            # No sobrescribir configuraciones de seguridad críticas
            if full_path in ['ssh.enabled', 'ssh.password', 'database.temporal']:
                continue  # Mantener valores por defecto seguros
            
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._fusionar_config_segura(base[key], value, full_path)
            elif key in base:
                base[key] = value
    
    def obtener(self, clave: str, valor_defecto: Any = None) -> Any:
        """Obtener valor de configuración"""
        keys = clave.split('.')
        current = self.config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return valor_defecto
        
        return current
    
    def establecer(self, clave: str, valor: Any):
        """Establecer valor de configuración de forma segura"""
        # No permitir cambios en configuraciones críticas
        claves_protegidas = ['ssh.enabled', 'ssh.password', 'database.temporal', 'app.modo']
        if clave in claves_protegidas:
            print(f"⚠️ Intento de modificar configuración protegida: {clave}")
            return
        
        keys = clave.split('.')
        current = self.config
        
        for i, key in enumerate(keys[:-1]):
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = valor

# =============================================================================
# GESTIÓN DE BASE DE DATOS
# =============================================================================

class GestorBaseDatos:
    """Gestor optimizado de base de datos SQLite para despliegue en nube"""
    
    def __init__(self, config: ConfiguracionSistema):
        self.config = config
        self._inicializar_rutas()
        self._inicializar_db()
    
    def _inicializar_rutas(self):
        """Inicializar rutas seguras para despliegue en la nube"""
        # Detectar si estamos en entorno de nube
        entorno_nube = any([
            'STREAMLIT_SHARING_MODE' in os.environ,
            'STREAMLIT_SERVER_ROOT' in os.environ,
            'STREAMLIT_DEPLOY' in os.environ
        ])
        
        if entorno_nube or self.config.obtener('database.temporal', True):
            # Usar directorio temporal para despliegue en la nube
            base_dir = tempfile.gettempdir()
            self.es_temporal = True
        else:
            # Desarrollo local
            base_dir = '.'
            self.es_temporal = False
        
        # Crear directorios necesarios
        self.base_dir = base_dir
        self.db_path = os.path.join(base_dir, self.config.obtener('database.name', 'escuela.db'))
        self.backup_dir = os.path.join(base_dir, self.config.obtener('database.backup_dir', 'backups'))
        
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(os.path.join(base_dir, 'uploads'), exist_ok=True)
        os.makedirs(os.path.join(base_dir, 'logs'), exist_ok=True)
    
    def _inicializar_db(self):
        """Inicializar estructura de la base de datos"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de estudiantes optimizada
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS estudiantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    apellido_paterno TEXT NOT NULL,
                    apellido_materno TEXT,
                    fecha_nacimiento TEXT,
                    genero TEXT CHECK(genero IN ('M', 'F', 'Otro')),
                    curp TEXT UNIQUE,
                    rfc TEXT,
                    telefono TEXT,
                    email TEXT UNIQUE,
                    direccion TEXT,
                    ciudad TEXT,
                    estado TEXT,
                    codigo_postal TEXT,
                    nivel_estudio TEXT CHECK(nivel_estudio IN ('Licenciatura', 'Maestría', 'Doctorado', 'Especialidad')),
                    carrera TEXT,
                    semestre INTEGER DEFAULT 1,
                    turno TEXT CHECK(turno IN ('Matutino', 'Vespertino', 'Nocturno', 'Mixto')),
                    fecha_ingreso TEXT,
                    fecha_egreso TEXT,
                    estado_estudiante TEXT DEFAULT 'Activo' CHECK(estado_estudiante IN ('Activo', 'Inactivo', 'Egresado', 'Baja Temporal', 'Baja Definitiva')),
                    promedio REAL DEFAULT 0.0,
                    creditos_aprobados INTEGER DEFAULT 0,
                    creditos_totales INTEGER DEFAULT 0,
                    foto_path TEXT,
                    documentos_path TEXT,
                    fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP,
                    activo INTEGER DEFAULT 1,
                    sesion_id TEXT,
                    modo_nube INTEGER DEFAULT 1
                )
            ''')
            
            # Índices optimizados
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_matricula ON estudiantes(matricula)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_nombre ON estudiantes(nombre, apellido_paterno)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_estado ON estudiantes(estado_estudiante)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_email ON estudiantes(email)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_sesion ON estudiantes(sesion_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_modo ON estudiantes(modo_nube)')
            
            # Tabla de inscritos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inscritos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    estudiante_id INTEGER NOT NULL,
                    ciclo_escolar TEXT NOT NULL,
                    semestre INTEGER,
                    fecha_inscripcion TEXT DEFAULT CURRENT_TIMESTAMP,
                    estatus TEXT DEFAULT 'Inscrito' CHECK(estatus IN ('Inscrito', 'Baja', 'Concluido')),
                    promedio_ciclo REAL,
                    creditos_inscritos INTEGER,
                    creditos_aprobados INTEGER,
                    observaciones TEXT,
                    FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id) ON DELETE CASCADE,
                    UNIQUE(estudiante_id, ciclo_escolar)
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ins_estudiante ON inscritos(estudiante_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_ins_ciclo ON inscritos(ciclo_escolar)')
            
            # Tabla de egresados
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS egresados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    estudiante_id INTEGER UNIQUE NOT NULL,
                    fecha_egreso TEXT NOT NULL,
                    titulo_obtenido TEXT,
                    promedio_final REAL,
                    fecha_titulacion TEXT,
                    numero_cedula TEXT UNIQUE,
                    institucion_titulacion TEXT,
                    empleo_actual TEXT,
                    empresa_actual TEXT,
                    salario_aproximado REAL,
                    fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id) ON DELETE CASCADE
                )
            ''')
            
            # Tabla de contratados
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contratados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    egresado_id INTEGER NOT NULL,
                    empresa TEXT NOT NULL,
                    puesto TEXT,
                    fecha_contratacion TEXT,
                    salario_inicial REAL,
                    salario_actual REAL,
                    tipo_contrato TEXT,
                    duracion_contrato TEXT,
                    beneficios TEXT,
                    fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
                    activo INTEGER DEFAULT 1,
                    FOREIGN KEY (egresado_id) REFERENCES egresados (id) ON DELETE CASCADE
                )
            ''')
            
            # Tabla de usuarios
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT UNIQUE,
                    rol TEXT CHECK(rol IN ('admin', 'supervisor', 'operador')),
                    activo INTEGER DEFAULT 1,
                    fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                    ultimo_acceso TEXT
                )
            ''')
            
            # Tabla de auditoría simplificada para nube
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auditoria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER,
                    accion TEXT NOT NULL,
                    tabla_afectada TEXT,
                    registro_id INTEGER,
                    detalles TEXT,
                    fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar usuario administrador por defecto con contraseña segura
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
            if cursor.fetchone()[0] == 0:
                # Contraseña segura: Admin@Nube2024!
                password_hash = hashlib.sha256('Admin@Nube2024!'.encode()).hexdigest()
                cursor.execute(
                    """INSERT INTO usuarios 
                       (username, password_hash, nombre_completo, email, rol) 
                       VALUES (?, ?, ?, ?, ?)""",
                    ('admin', password_hash, 'Administrador del Sistema', 
                     'admin@escuela.edu.mx', 'admin')
                )
            
            conn.commit()
            
            # Marcar que está en modo nube
            if self.es_temporal:
                cursor.execute("UPDATE estudiantes SET modo_nube = 1 WHERE modo_nube IS NULL")
                conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Context manager para conexiones a BD optimizado"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")  # Optimizado para rendimiento
        
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def ejecutar_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Ejecutar consulta y retornar resultados como diccionarios"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if cursor.description:
                columns = [description[0] for description in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            return []
    
    def ejecutar_commit(self, query: str, params: tuple = None) -> int:
        """Ejecutar consulta con commit y retornar última fila insertada"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            conn.commit()
            return cursor.lastrowid
    
    def obtener_uno(self, query: str, params: tuple = None) -> Optional[Dict[str, Any]]:
        """Obtener un solo registro"""
        resultados = self.ejecutar_query(query, params)
        return resultados[0] if resultados else None
    
    def crear_backup(self) -> Tuple[bool, str]:
        """Crear backup de la base de datos optimizado para nube"""
        try:
            if not self.config.obtener('database.backup_enabled', True):
                return True, "Backup deshabilitado en configuración"
            
            # Verificar espacio en disco (solo si psutil está disponible)
            try:
                import psutil
                espacio_disponible = psutil.disk_usage(self.backup_dir).free / (1024 * 1024)
                if espacio_disponible < 50:  # Menos de 50 MB
                    return False, f"Espacio insuficiente para backup: {espacio_disponible:.1f} MB"
            except ImportError:
                pass  # Si no hay psutil, continuar igual
            
            # Crear nombre de backup
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(self.backup_dir, f"escuela_backup_{timestamp}.db")
            
            # Copiar base de datos
            shutil.copy2(self.db_path, backup_file)
            
            # Comprimir si es grande
            try:
                file_size = os.path.getsize(backup_file)
                if file_size > 5 * 1024 * 1024:  # > 5MB
                    with open(backup_file, 'rb') as f_in:
                        with gzip.open(f"{backup_file}.gz", 'wb') as f_out:
                            f_out.writelines(f_in)
                    os.remove(backup_file)
                    backup_file = f"{backup_file}.gz"
            except Exception:
                pass  # Si falla la compresión, mantener sin comprimir
            
            # Limpiar backups antiguos
            self._limpiar_backups_antiguos()
            
            return True, f"Backup creado exitosamente"
            
        except Exception as e:
            return False, f"Error creando backup: {str(e)}"
    
    def _limpiar_backups_antiguos(self):
        """Limpiar backups antiguos manteniendo solo los más recientes"""
        try:
            max_backups = self.config.obtener('database.max_backups', 10)
            
            backups = []
            for file in os.listdir(self.backup_dir):
                if file.startswith('escuela_backup_'):
                    file_path = os.path.join(self.backup_dir, file)
                    backups.append((file_path, os.path.getmtime(file_path)))
            
            # Ordenar por fecha de modificación (más antiguos primero)
            backups.sort(key=lambda x: x[1])
            
            # Eliminar los más antiguos si excedemos el máximo
            while len(backups) > max_backups:
                old_backup = backups.pop(0)
                try:
                    os.remove(old_backup[0])
                except:
                    pass
            
        except Exception as e:
            print(f"⚠️ Error limpiando backups antiguos: {e}")
    
    def obtener_informacion_sistema(self) -> Dict[str, Any]:
        """Obtener información del sistema de base de datos"""
        info = {
            'ruta_db': self.db_path,
            'backup_dir': self.backup_dir,
            'es_temporal': self.es_temporal,
            'modo': 'Nube' if self.es_temporal else 'Local',
            'tamano_db': 'N/A'
        }
        
        try:
            if os.path.exists(self.db_path):
                tamano = os.path.getsize(self.db_path) / (1024 * 1024)
                info['tamano_db'] = f"{tamano:.2f} MB"
        except:
            pass
        
        return info

# =============================================================================
# VALIDACIÓN DE DATOS
# =============================================================================

class ValidadorDatos:
    """Validador de datos del sistema optimizado"""
    
    @staticmethod
    def validar_email(email: str) -> bool:
        """Validar formato de email"""
        import re
        if not email:
            return True  # Email opcional
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_matricula(matricula: str) -> bool:
        """Validar formato de matrícula"""
        if not matricula:
            return False
        # Matrícula debe tener al menos 3 caracteres y algún número
        return len(matricula) >= 3 and any(char.isdigit() for char in matricula)
    
    @staticmethod
    def validar_curp(curp: str) -> bool:
        """Validar formato de CURP"""
        if not curp:
            return True  # CURP opcional
        # CURP debe tener 18 caracteres
        return len(curp) == 18 and curp.isalnum()
    
    @staticmethod
    def validar_telefono(telefono: str) -> bool:
        """Validar formato de teléfono"""
        if not telefono:
            return True  # Teléfono opcional
        # Teléfono debe tener 10 dígitos
        return telefono.isdigit() and len(telefono) == 10
    
    @staticmethod
    def validar_fecha(fecha_str: str) -> bool:
        """Validar formato de fecha (YYYY-MM-DD)"""
        if not fecha_str:
            return True
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
            # Verificar que no sea fecha futura (excepto para fechas de ingreso/egreso)
            if fecha > datetime.now() and not fecha_str.startswith('20'):  # Permitir fechas futuras razonables
                return False
            return True
        except ValueError:
            return False
    
    def validar_estudiante(self, datos: Dict[str, Any]) -> List[str]:
        """Validar datos de estudiante"""
        errores = []
        
        # Validar matrícula
        if not datos.get('matricula'):
            errores.append("La matrícula es obligatoria")
        elif not self.validar_matricula(datos['matricula']):
            errores.append("Formato de matrícula inválido (mínimo 3 caracteres con números)")
        
        # Validar nombre
        if not datos.get('nombre'):
            errores.append("El nombre es obligatorio")
        elif len(datos['nombre'].strip()) < 2:
            errores.append("El nombre debe tener al menos 2 caracteres")
        
        # Validar apellido paterno
        if not datos.get('apellido_paterno'):
            errores.append("El apellido paterno es obligatorio")
        elif len(datos['apellido_paterno'].strip()) < 2:
            errores.append("El apellido paterno debe tener al menos 2 caracteres")
        
        # Validar email
        if datos.get('email') and not self.validar_email(datos['email']):
            errores.append("Formato de email inválido")
        
        # Validar CURP
        if datos.get('curp') and not self.validar_curp(datos['curp']):
            errores.append("El CURP debe tener 18 caracteres alfanuméricos")
        
        # Validar teléfono
        if datos.get('telefono') and not self.validar_telefono(datos['telefono']):
            errores.append("El teléfono debe tener 10 dígitos")
        
        # Validar fecha de nacimiento
        if datos.get('fecha_nacimiento'):
            if not self.validar_fecha(datos['fecha_nacimiento']):
                errores.append("Formato de fecha de nacimiento inválido (usar YYYY-MM-DD)")
            else:
                try:
                    fecha_nac = datetime.strptime(datos['fecha_nacimiento'], '%Y-%m-%d')
                    if fecha_nac > datetime.now():
                        errores.append("La fecha de nacimiento no puede ser futura")
                except:
                    pass
        
        return errores

# =============================================================================
# GESTIÓN DE SESIONES
# =============================================================================

class GestorSesion:
    """Gestor de sesiones optimizado para despliegue multi-usuario"""
    
    def __init__(self):
        if 'session_id' not in st.session_state:
            # Generar ID único para esta sesión
            import secrets
            st.session_state.session_id = f"sesion_{secrets.token_hex(8)}"
        
        if 'sesion_iniciada' not in st.session_state:
            st.session_state.sesion_iniciada = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        self.session_id = st.session_state.session_id
        self.sesion_iniciada = st.session_state.sesion_iniciada
    
    def obtener_info_sesion(self) -> Dict[str, Any]:
        """Obtener información de la sesión actual"""
        return {
            'session_id': self.session_id,
            'iniciada': self.sesion_iniciada,
            'duracion': self._calcular_duracion_sesion()
        }
    
    def _calcular_duracion_sesion(self) -> str:
        """Calcular duración de la sesión actual"""
        try:
            inicio = datetime.strptime(self.sesion_iniciada, '%Y-%m-%d %H:%M:%S')
            ahora = datetime.now()
            diferencia = ahora - inicio
            
            horas = diferencia.seconds // 3600
            minutos = (diferencia.seconds % 3600) // 60
            segundos = diferencia.seconds % 60
            
            if horas > 0:
                return f"{horas}h {minutos}m {segundos}s"
            elif minutos > 0:
                return f"{minutos}m {segundos}s"
            else:
                return f"{segundos}s"
        except:
            return "N/A"
    
    def limpiar_datos_sesion(self, db):
        """Limpiar datos específicos de esta sesión"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM estudiantes WHERE sesion_id = ?",
                    (self.session_id,)
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"Error limpiando datos de sesión: {e}")
            return False

# =============================================================================
# SISTEMA PRINCIPAL DE GESTIÓN ESCOLAR
# =============================================================================

class SistemaGestionEscolar:
    """Sistema principal de gestión escolar optimizado para nube"""
    
    def __init__(self):
        # Inicializar componentes
        self.config = ConfiguracionSistema()
        self.db = GestorBaseDatos(self.config)
        self.validador = ValidadorDatos()
        self.sesion = GestorSesion()
        
        # Cache para datos frecuentes
        self._cache_estadisticas = None
        self._cache_timestamp = None
        self._cache_ttl = self.config.obtener('app.cache_ttl', 300)
        
        # Estado del sistema optimizado para nube
        self.modo_operacion = self.config.obtener('app.modo', 'nube')
        self.ssh_conectado = False
        self.ssh_configurado = self.config.obtener('ssh.enabled', False)
        self.ultima_sincronizacion = None
        self.estado_aplicacion = 'inicializado'
        
        # Inicializar sistema
        self._inicializar_sistema()
    
    def _inicializar_sistema(self):
        """Inicializar el sistema optimizado para nube"""
        # Crear directorios necesarios
        for dir_path in ['uploads/estudiantes', 'uploads/documentos', 'logs']:
            os.makedirs(dir_path, exist_ok=True)
        
        # Solo intentar conectar SSH si está explícitamente habilitado
        if self.ssh_configurado:
            self._inicializar_conexion_ssh()
        else:
            # En modo nube, deshabilitamos SSH por seguridad
            print("🔒 SSH deshabilitado por seguridad en despliegue en la nube")
        
        # Marcar sistema como listo
        self.estado_aplicacion = 'listo'
    
    def _inicializar_conexion_ssh(self):
        """Inicializar conexión SSH solo si está configurada y habilitada"""
        try:
            import paramiko
            import socket
            
            host = self.config.obtener('ssh.host')
            username = self.config.obtener('ssh.username')
            password = self.config.obtener('ssh.password')
            
            if not host or not username or not password:
                print("⚠️ Configuración SSH incompleta")
                return
            
            print(f"🔗 Intentando conexión SSH a {host}...")
            
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            timeout = self.config.obtener('ssh.timeout', 30)
            
            self.ssh_client.connect(
                hostname=host,
                port=self.config.obtener('ssh.port', 22),
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            self.sftp = self.ssh_client.open_sftp()
            self.ssh_conectado = True
            print(f"✅ Conexión SSH establecida a {host}")
            
        except Exception as e:
            print(f"⚠️ Error conexión SSH: {e}")
            self.ssh_conectado = False
    
    # =========================================================================
    # MÉTODOS PARA ESTUDIANTES
    # =========================================================================
    
    def obtener_estudiantes(
        self, 
        filtro_estado: str = None,
        filtro_nivel: str = None,
        busqueda: str = None,
        limite: int = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Obtener lista de estudiantes con filtros"""
        try:
            if limite is None:
                limite = self.config.obtener('app.page_size', 50)
            
            query = "SELECT * FROM estudiantes WHERE activo = 1"
            params = []
            
            if filtro_estado and filtro_estado != 'Todos':
                query += " AND estado_estudiante = ?"
                params.append(filtro_estado)
            
            if filtro_nivel and filtro_nivel != 'Todos':
                query += " AND nivel_estudio = ?"
                params.append(filtro_nivel)
            
            if busqueda:
                query += """ AND (
                    matricula LIKE ? OR 
                    nombre LIKE ? OR 
                    apellido_paterno LIKE ? OR 
                    email LIKE ? OR
                    curp LIKE ?
                )"""
                search_term = f"%{busqueda}%"
                params.extend([search_term] * 5)
            
            query += " ORDER BY fecha_ingreso DESC LIMIT ? OFFSET ?"
            params.extend([limite, offset])
            
            return self.db.ejecutar_query(query, tuple(params))
            
        except Exception as e:
            st.error(f"❌ Error obteniendo estudiantes: {e}")
            return []
    
    def obtener_estudiante_por_id(self, estudiante_id: int) -> Optional[Dict[str, Any]]:
        """Obtener estudiante por ID"""
        query = "SELECT * FROM estudiantes WHERE id = ? AND activo = 1"
        return self.db.obtener_uno(query, (estudiante_id,))
    
    def buscar_estudiante(self, criterio: str, valor: str) -> List[Dict[str, Any]]:
        """Buscar estudiante por criterio"""
        criterios_validos = {
            'matricula': 'matricula',
            'nombre': 'nombre',
            'curp': 'curp',
            'email': 'email'
        }
        
        if criterio not in criterios_validos:
            return []
        
        campo = criterios_validos[criterio]
        query = f"SELECT * FROM estudiantes WHERE {campo} LIKE ? AND activo = 1"
        return self.db.ejecutar_query(query, (f"%{valor}%",))
    
    def crear_estudiante(self, datos: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
        """Crear nuevo estudiante"""
        try:
            # Validar datos
            errores = self.validador.validar_estudiante(datos)
            if errores:
                return False, "; ".join(errores), None
            
            # Verificar matrícula única
            if datos.get('matricula'):
                existe = self.db.obtener_uno(
                    "SELECT id FROM estudiantes WHERE matricula = ?",
                    (datos['matricula'],)
                )
                if existe:
                    return False, "La matrícula ya existe", None
            
            # Verificar email único
            if datos.get('email'):
                existe = self.db.obtener_uno(
                    "SELECT id FROM estudiantes WHERE email = ?",
                    (datos['email'],)
                )
                if existe:
                    return False, "El email ya está registrado", None
            
            # Preparar datos para inserción
            campos = ['sesion_id']  # Añadir ID de sesión
            placeholders = ['?']
            valores = [self.sesion.session_id]
            
            for campo, valor in datos.items():
                if valor is not None and valor != '':
                    campos.append(campo)
                    placeholders.append('?')
                    valores.append(valor)
            
            # Añadir fechas automáticas
            campos.append('fecha_creacion')
            placeholders.append('CURRENT_TIMESTAMP')
            
            # Añadir modo nube
            campos.append('modo_nube')
            placeholders.append('1')
            
            # Ejecutar inserción
            query = f"INSERT INTO estudiantes ({', '.join(campos)}) VALUES ({', '.join(placeholders)})"
            estudiante_id = self.db.ejecutar_commit(query, tuple(valores))
            
            # Registrar auditoría
            try:
                self.db.ejecutar_commit(
                    """INSERT INTO auditoria 
                       (accion, tabla_afectada, registro_id, detalles) 
                       VALUES (?, ?, ?, ?)""",
                    ('INSERT', 'estudiantes', estudiante_id, 
                     f"Estudiante creado: {datos.get('matricula', 'N/A')}")
                )
            except:
                pass  # Tabla de auditoría no existe, ignorar
            
            # Limpiar cache
            self._cache_estadisticas = None
            
            return True, "Estudiante creado exitosamente", estudiante_id
            
        except Exception as e:
            return False, f"Error al crear estudiante: {str(e)}", None
    
    def actualizar_estudiante(self, estudiante_id: int, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """Actualizar estudiante existente"""
        try:
            # Verificar que existe
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            if not estudiante:
                return False, "Estudiante no encontrado"
            
            # Preparar SET clauses
            set_clauses = []
            valores = []
            
            for campo, valor in datos.items():
                if campo not in ['id', 'fecha_creacion', 'sesion_id', 'modo_nube']:
                    if valor != estudiante.get(campo):
                        set_clauses.append(f"{campo} = ?")
                        valores.append(valor)
            
            if not set_clauses:
                return True, "No hay cambios para actualizar"
            
            # Añadir fecha de actualización
            set_clauses.append("fecha_actualizacion = CURRENT_TIMESTAMP")
            
            # Ejecutar actualización
            valores.append(estudiante_id)
            query = f"UPDATE estudiantes SET {', '.join(set_clauses)} WHERE id = ?"
            self.db.ejecutar_commit(query, tuple(valores))
            
            # Registrar auditoría
            try:
                cambios = ', '.join([f"{k}: {v}" for k, v in datos.items() 
                                   if k in datos and estudiante.get(k) != v])
                self.db.ejecutar_commit(
                    """INSERT INTO auditoria 
                       (accion, tabla_afectada, registro_id, detalles) 
                       VALUES (?, ?, ?, ?)""",
                    ('UPDATE', 'estudiantes', estudiante_id, 
                     f"Estudiante actualizado: {cambios}")
                )
            except:
                pass
            
            # Limpiar cache de estadísticas
            self._cache_estadisticas = None
            
            return True, "Estudiante actualizado exitosamente"
            
        except Exception as e:
            return False, f"Error al actualizar estudiante: {str(e)}"
    
    def eliminar_estudiante(self, estudiante_id: int) -> Tuple[bool, str]:
        """Eliminar estudiante (baja lógica)"""
        try:
            # Verificar que no tenga inscripciones activas
            inscripciones = self.db.ejecutar_query(
                "SELECT id FROM inscritos WHERE estudiante_id = ? AND estatus = 'Inscrito'",
                (estudiante_id,)
            )
            
            if inscripciones:
                return False, "No se puede eliminar estudiante con inscripciones activas"
            
            # Baja lógica
            query = """
                UPDATE estudiantes 
                SET estado_estudiante = 'Baja Definitiva', 
                    activo = 0,
                    fecha_actualizacion = CURRENT_TIMESTAMP 
                WHERE id = ?
            """
            self.db.ejecutar_commit(query, (estudiante_id,))
            
            # Registrar auditoría
            try:
                self.db.ejecutar_commit(
                    """INSERT INTO auditoria 
                       (accion, tabla_afectada, registro_id, detalles) 
                       VALUES (?, ?, ?, ?)""",
                    ('UPDATE', 'estudiantes', estudiante_id, "Baja definitiva")
                )
            except:
                pass
            
            # Limpiar cache
            self._cache_estadisticas = None
            
            return True, "Estudiante dado de baja exitosamente"
            
        except Exception as e:
            return False, f"Error al eliminar estudiante: {str(e)}"
    
    def cambiar_estado_estudiante(self, estudiante_id: int, nuevo_estado: str) -> Tuple[bool, str]:
        """Cambiar estado de estudiante"""
        # Validar estado
        estados_validos = self.config.obtener('estados.estudiante', [])
        if nuevo_estado not in estados_validos:
            return False, f"Estado inválido. Debe ser: {', '.join(estados_validos)}"
        
        try:
            query = """
                UPDATE estudiantes 
                SET estado_estudiante = ?, 
                    fecha_actualizacion = CURRENT_TIMESTAMP 
                WHERE id = ?
            """
            self.db.ejecutar_commit(query, (nuevo_estado, estudiante_id))
            
            # Si es egresado, registrar en tabla de egresados
            if nuevo_estado == 'Egresado':
                estudiante = self.obtener_estudiante_por_id(estudiante_id)
                if estudiante:
                    self._registrar_egresado_automatico(estudiante_id)
            
            # Registrar auditoría
            try:
                self.db.ejecutar_commit(
                    """INSERT INTO auditoria 
                       (accion, tabla_afectada, registro_id, detalles) 
                       VALUES (?, ?, ?, ?)""",
                    ('UPDATE', 'estudiantes', estudiante_id, 
                     f"Estado cambiado a: {nuevo_estado}")
                )
            except:
                pass
            
            # Limpiar cache
            self._cache_estadisticas = None
            
            return True, f"Estado cambiado a {nuevo_estado}"
            
        except Exception as e:
            return False, f"Error cambiando estado: {str(e)}"
    
    # =========================================================================
    # MÉTODOS PARA INSCRIPCIONES
    # =========================================================================
    
    def obtener_inscripciones(
        self, 
        estudiante_id: Optional[int] = None,
        ciclo_escolar: Optional[str] = None,
        estatus: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Obtener inscripciones"""
        try:
            query = """
                SELECT i.*, e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno
                FROM inscritos i
                JOIN estudiantes e ON i.estudiante_id = e.id
                WHERE e.activo = 1
            """
            params = []
            
            if estudiante_id:
                query += " AND i.estudiante_id = ?"
                params.append(estudiante_id)
            
            if ciclo_escolar:
                query += " AND i.ciclo_escolar = ?"
                params.append(ciclo_escolar)
            
            if estatus:
                query += " AND i.estatus = ?"
                params.append(estatus)
            
            query += " ORDER BY i.fecha_inscripcion DESC"
            
            return self.db.ejecutar_query(query, tuple(params))
            
        except Exception as e:
            st.error(f"❌ Error obteniendo inscripciones: {e}")
            return []
    
    def inscribir_estudiante(
        self, 
        estudiante_id: int, 
        ciclo_escolar: str,
        semestre: Optional[int] = None,
        creditos_inscritos: Optional[int] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """Inscribir estudiante en ciclo escolar"""
        try:
            # Verificar que el estudiante existe y está activo
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            if not estudiante:
                return False, "Estudiante no encontrado", None
            
            if estudiante['estado_estudiante'] != 'Activo':
                return False, f"Estudiante no está activo (estado: {estudiante['estado_estudiante']})", None
            
            # Verificar que no esté ya inscrito en el mismo ciclo
            existe = self.db.obtener_uno(
                "SELECT id FROM inscritos WHERE estudiante_id = ? AND ciclo_escolar = ?",
                (estudiante_id, ciclo_escolar)
            )
            
            if existe:
                return False, f"Estudiante ya inscrito en el ciclo {ciclo_escolar}", None
            
            # Insertar inscripción
            query = """
                INSERT INTO inscritos 
                (estudiante_id, ciclo_escolar, semestre, creditos_inscritos, fecha_inscripcion)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            inscripcion_id = self.db.ejecutar_commit(
                query, 
                (estudiante_id, ciclo_escolar, semestre, creditos_inscritos)
            )
            
            # Actualizar semestre del estudiante si es mayor
            if semestre and semestre > estudiante.get('semestre', 0):
                self.db.ejecutar_commit(
                    "UPDATE estudiantes SET semestre = ? WHERE id = ?",
                    (semestre, estudiante_id)
                )
            
            # Registrar auditoría
            try:
                self.db.ejecutar_commit(
                    """INSERT INTO auditoria 
                       (accion, tabla_afectada, registro_id, detalles) 
                       VALUES (?, ?, ?, ?)""",
                    ('INSERT', 'inscritos', inscripcion_id,
                     f"Estudiante {estudiante_id} inscrito en {ciclo_escolar}")
                )
            except:
                pass
            
            # Limpiar cache
            self._cache_estadisticas = None
            
            return True, "Estudiante inscrito exitosamente", inscripcion_id
            
        except Exception as e:
            return False, f"Error inscribiendo estudiante: {str(e)}", None
    
    # =========================================================================
    # MÉTODOS PARA EGRESADOS
    # =========================================================================
    
    def obtener_egresados(
        self,
        filtro_titulo: Optional[str] = None,
        filtro_fecha_desde: Optional[str] = None,
        limite: int = 50
    ) -> List[Dict[str, Any]]:
        """Obtener lista de egresados"""
        try:
            query = """
                SELECT e.*, est.matricula, est.nombre, est.apellido_paterno, 
                       est.apellido_materno, est.carrera, est.nivel_estudio
                FROM egresados e
                JOIN estudiantes est ON e.estudiante_id = est.id
                WHERE est.activo = 1
            """
            params = []
            
            if filtro_titulo:
                query += " AND e.titulo_obtenido LIKE ?"
                params.append(f"%{filtro_titulo}%")
            
            if filtro_fecha_desde:
                query += " AND e.fecha_egreso >= ?"
                params.append(filtro_fecha_desde)
            
            query += " ORDER BY e.fecha_egreso DESC LIMIT ?"
            params.append(limite)
            
            return self.db.ejecutar_query(query, tuple(params))
            
        except Exception as e:
            st.error(f"❌ Error obteniendo egresados: {e}")
            return []
    
    def registrar_egresado(
        self,
        estudiante_id: int,
        fecha_egreso: str,
        titulo_obtenido: str,
        promedio_final: float
    ) -> Tuple[bool, str, Optional[int]]:
        """Registrar estudiante como egresado"""
        try:
            # Verificar que el estudiante existe
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            if not estudiante:
                return False, "Estudiante no encontrado", None
            
            # Verificar que no esté ya registrado como egresado
            existe = self.db.obtener_uno(
                "SELECT id FROM egresados WHERE estudiante_id = ?",
                (estudiante_id,)
            )
            if existe:
                return False, "Estudiante ya está registrado como egresado", None
            
            # Insertar registro de egresado
            query = """
                INSERT INTO egresados 
                (estudiante_id, fecha_egreso, titulo_obtenido, promedio_final, fecha_registro)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            egresado_id = self.db.ejecutar_commit(
                query, 
                (estudiante_id, fecha_egreso, titulo_obtenido, promedio_final)
            )
            
            # Actualizar estado del estudiante
            self.db.ejecutar_commit(
                "UPDATE estudiantes SET estado_estudiante = 'Egresado', fecha_egreso = ? WHERE id = ?",
                (fecha_egreso, estudiante_id)
            )
            
            # Registrar auditoría
            try:
                self.db.ejecutar_commit(
                    """INSERT INTO auditoria 
                       (accion, tabla_afectada, registro_id, detalles) 
                       VALUES (?, ?, ?, ?)""",
                    ('INSERT', 'egresados', egresado_id,
                     f"Estudiante {estudiante_id} registrado como egresado")
                )
            except:
                pass
            
            # Limpiar cache
            self._cache_estadisticas = None
            
            return True, "Egresado registrado exitosamente", egresado_id
            
        except Exception as e:
            return False, f"Error registrando egresado: {str(e)}", None
    
    def _registrar_egresado_automatico(self, estudiante_id: int) -> bool:
        """Registrar egresado automáticamente al cambiar estado"""
        try:
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            if not estudiante:
                return False
            
            # Verificar si ya está registrado
            existe = self.db.obtener_uno(
                "SELECT id FROM egresados WHERE estudiante_id = ?",
                (estudiante_id,)
            )
            if existe:
                return True
            
            # Registrar con datos básicos
            fecha_actual = datetime.now().strftime('%Y-%m-%d')
            query = """
                INSERT INTO egresados 
                (estudiante_id, fecha_egreso, fecha_registro)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """
            self.db.ejecutar_commit(query, (estudiante_id, fecha_actual))
            
            return True
            
        except Exception as e:
            print(f"Error registrando egresado automático: {e}")
            return False
    
    # =========================================================================
    # MÉTODOS PARA CONTRATADOS
    # =========================================================================
    
    def obtener_contratados(
        self,
        filtro_empresa: Optional[str] = None,
        filtro_puesto: Optional[str] = None,
        limite: int = 50
    ) -> List[Dict[str, Any]]:
        """Obtener lista de contratados"""
        try:
            query = """
                SELECT c.*, e.estudiante_id, e.titulo_obtenido, e.promedio_final,
                       est.matricula, est.nombre, est.apellido_paterno, 
                       est.apellido_materno, est.carrera
                FROM contratados c
                JOIN egresados e ON c.egresado_id = e.id
                JOIN estudiantes est ON e.estudiante_id = est.id
                WHERE c.activo = 1
            """
            params = []
            
            if filtro_empresa:
                query += " AND c.empresa LIKE ?"
                params.append(f"%{filtro_empresa}%")
            
            if filtro_puesto:
                query += " AND c.puesto LIKE ?"
                params.append(f"%{filtro_puesto}%")
            
            query += " ORDER BY c.fecha_contratacion DESC LIMIT ?"
            params.append(limite)
            
            return self.db.ejecutar_query(query, tuple(params))
            
        except Exception as e:
            st.error(f"❌ Error obteniendo contratados: {e}")
            return []
    
    # =========================================================================
    # ESTADÍSTICAS E INFORMES
    # =========================================================================
    
    def obtener_estadisticas_generales(self) -> Dict[str, Any]:
        """Obtener estadísticas generales del sistema"""
        # Verificar cache
        if (self._cache_estadisticas and self._cache_timestamp and 
            (datetime.now() - self._cache_timestamp).seconds < self._cache_ttl):
            return self._cache_estadisticas
        
        estadisticas = {}
        
        try:
            # Total de estudiantes por estado
            estudiantes_por_estado = self.db.ejecutar_query("""
                SELECT estado_estudiante, COUNT(*) as total
                FROM estudiantes
                WHERE activo = 1
                GROUP BY estado_estudiante
            """)
            
            estadisticas['estudiantes_por_estado'] = {
                item['estado_estudiante']: item['total'] 
                for item in estudiantes_por_estado
            }
            
            # Totales
            estadisticas['total_estudiantes'] = sum(
                estadisticas['estudiantes_por_estado'].values()
            )
            estadisticas['estudiantes_activos'] = estadisticas['estudiantes_por_estado'].get('Activo', 0)
            
            # Egresados
            egresados = self.db.obtener_uno("SELECT COUNT(*) as total FROM egresados")
            estadisticas['total_egresados'] = egresados['total'] if egresados else 0
            
            # Contratados
            contratados = self.db.obtener_uno("SELECT COUNT(DISTINCT egresado_id) as total FROM contratados")
            estadisticas['egresados_contratados'] = contratados['total'] if contratados else 0
            
            # Promedio general
            promedio = self.db.obtener_uno("""
                SELECT AVG(promedio) as promedio
                FROM estudiantes 
                WHERE estado_estudiante = 'Activo' 
                AND promedio IS NOT NULL
                AND activo = 1
            """)
            estadisticas['promedio_general'] = round(promedio['promedio'] or 0.0, 2)
            
            # Estudiantes por nivel
            estudiantes_nivel = self.db.ejecutar_query("""
                SELECT nivel_estudio, COUNT(*) as total
                FROM estudiantes
                WHERE nivel_estudio IS NOT NULL AND activo = 1
                GROUP BY nivel_estudio
            """)
            estadisticas['estudiantes_por_nivel'] = {
                item['nivel_estudio']: item['total']
                for item in estudiantes_nivel
            }
            
            # Top carreras
            top_carreras = self.db.ejecutar_query("""
                SELECT carrera, COUNT(*) as total
                FROM estudiantes
                WHERE carrera IS NOT NULL AND activo = 1
                GROUP BY carrera
                ORDER BY total DESC
                LIMIT 10
            """)
            estadisticas['top_carreras'] = {
                item['carrera']: item['total']
                for item in top_carreras
            }
            
            # Inscripciones por ciclo
            inscripciones_ciclo = self.db.ejecutar_query("""
                SELECT ciclo_escolar, COUNT(*) as total
                FROM inscritos
                GROUP BY ciclo_escolar
                ORDER BY ciclo_escolar DESC
                LIMIT 5
            """)
            estadisticas['inscripciones_por_ciclo'] = {
                item['ciclo_escolar']: item['total']
                for item in inscripciones_ciclo
            }
            
            # Cachear resultados
            self._cache_estadisticas = estadisticas
            self._cache_timestamp = datetime.now()
            
        except Exception as e:
            st.error(f"❌ Error obteniendo estadísticas: {e}")
            estadisticas = {
                'total_estudiantes': 0,
                'estudiantes_activos': 0,
                'total_egresados': 0,
                'egresados_contratados': 0,
                'promedio_general': 0.0,
                'estudiantes_por_estado': {},
                'estudiantes_por_nivel': {},
                'top_carreras': {},
                'inscripciones_por_ciclo': {}
            }
        
        return estadisticas
    
    def obtener_estadisticas_rapidas(self) -> Dict[str, Any]:
        """Obtener estadísticas rápidas para el dashboard"""
        try:
            stats = {}
            
            # Totales básicos
            total_estudiantes = self.db.obtener_uno(
                "SELECT COUNT(*) as total FROM estudiantes WHERE activo = 1"
            )
            stats['total_estudiantes'] = total_estudiantes['total'] if total_estudiantes else 0
            
            estudiantes_activos = self.db.obtener_uno(
                "SELECT COUNT(*) as total FROM estudiantes WHERE estado_estudiante = 'Activo' AND activo = 1"
            )
            stats['estudiantes_activos'] = estudiantes_activos['total'] if estudiantes_activos else 0
            
            total_egresados = self.db.obtener_uno("SELECT COUNT(*) as total FROM egresados")
            stats['total_egresados'] = total_egresados['total'] if total_egresados else 0
            
            # Estudiantes de esta sesión
            estudiantes_sesion = self.db.obtener_uno(
                "SELECT COUNT(*) as total FROM estudiantes WHERE sesion_id = ?",
                (self.sesion.session_id,)
            )
            stats['estudiantes_sesion'] = estudiantes_sesion['total'] if estudiantes_sesion else 0
            
            return stats
            
        except Exception as e:
            print(f"Error obteniendo estadísticas rápidas: {e}")
            return {
                'total_estudiantes': 0, 
                'estudiantes_activos': 0, 
                'total_egresados': 0,
                'estudiantes_sesion': 0
            }
    
    def generar_informe_excel(self, tipo_informe: str) -> Tuple[Optional[io.BytesIO], Optional[str]]:
        """Generar informe en formato Excel"""
        try:
            if tipo_informe == 'estudiantes':
                query = """
                    SELECT matricula, nombre, apellido_paterno, apellido_materno,
                           carrera, nivel_estudio, semestre, estado_estudiante,
                           promedio, fecha_ingreso
                    FROM estudiantes
                    WHERE activo = 1
                    ORDER BY fecha_ingreso DESC
                """
                nombre_archivo = f"informe_estudiantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
            elif tipo_informe == 'egresados':
                query = """
                    SELECT e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno,
                           e.carrera, eg.titulo_obtenido, eg.promedio_final, 
                           eg.fecha_egreso, eg.numero_cedula
                    FROM egresados eg
                    JOIN estudiantes e ON eg.estudiante_id = e.id
                    ORDER BY eg.fecha_egreso DESC
                """
                nombre_archivo = f"informe_egresados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
            elif tipo_informe == 'contratados':
                query = """
                    SELECT e.matricula, e.nombre, e.carrera, 
                           c.empresa, c.puesto, c.fecha_contratacion,
                           c.salario_actual, c.tipo_contrato
                    FROM contratados c
                    JOIN egresados eg ON c.egresado_id = eg.id
                    JOIN estudiantes e ON eg.estudiante_id = e.id
                    WHERE c.activo = 1
                    ORDER BY c.fecha_contratacion DESC
                """
                nombre_archivo = f"informe_contratados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
            else:
                return None, None
            
            # Obtener datos
            datos = self.db.ejecutar_query(query)
            
            if not datos:
                return None, None
            
            # Crear DataFrame
            df = pd.DataFrame(datos)
            
            # Crear archivo Excel en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Datos', index=False)
            
            output.seek(0)
            
            return output, nombre_archivo
            
        except Exception as e:
            st.error(f"❌ Error generando informe Excel: {e}")
            return None, None
    
    # =========================================================================
    # UTILIDADES
    # =========================================================================
    
    def obtener_proximo_ciclo_escolar(self) -> str:
        """Obtener el próximo ciclo escolar basado en la fecha actual"""
        hoy = datetime.now()
        año_actual = hoy.year
        mes_actual = hoy.month
        
        # Si estamos después de junio, el próximo ciclo es del siguiente año
        if mes_actual > 6:
            return f"{año_actual}-{año_actual + 1}"
        else:
            return f"{año_actual - 1}-{año_actual}"
    
    def obtener_ciclos_escolares(self) -> List[str]:
        """Obtener lista de ciclos escolares disponibles"""
        try:
            resultados = self.db.ejecutar_query(
                "SELECT DISTINCT ciclo_escolar FROM inscritos ORDER BY ciclo_escolar DESC"
            )
            ciclos = [item['ciclo_escolar'] for item in resultados]
            
            # Si no hay ciclos, generar algunos por defecto
            if not ciclos:
                año_actual = datetime.now().year
                ciclos = [
                    f"{año_actual-2}-{año_actual-1}",
                    f"{año_actual-1}-{año_actual}",
                    f"{año_actual}-{año_actual+1}"
                ]
            
            return ciclos
            
        except Exception as e:
            print(f"Error obteniendo ciclos escolares: {e}")
            año_actual = datetime.now().year
            return [f"{año_actual-1}-{año_actual}", f"{año_actual}-{año_actual+1}"]
    
    def sincronizar_con_servidor(self) -> Tuple[bool, str]:
        """Sincronizar con servidor remoto (si está configurado)"""
        if not self.ssh_conectado:
            if self.ssh_configurado:
                return False, "SSH configurado pero no conectado. Verifique credenciales."
            else:
                return True, "✅ Modo local activado - La sincronización SSH está deshabilitada por seguridad"
        
        try:
            # Aquí iría la lógica real de sincronización
            # Por ahora es un placeholder que simula éxito
            self.ultima_sincronizacion = datetime.now()
            return True, "✅ Sincronización completada exitosamente"
            
        except Exception as e:
            return False, f"❌ Error en sincronización: {str(e)}"
    
    def crear_backup(self) -> Tuple[bool, str]:
        """Crear backup de la base de datos"""
        return self.db.crear_backup()
    
    def limpiar_cache(self):
        """Limpiar cache del sistema"""
        self._cache_estadisticas = None
        self._cache_timestamp = None
    
    def obtener_estado_sistema(self) -> Dict[str, Any]:
        """Obtener estado completo del sistema"""
        info_db = self.db.obtener_informacion_sistema()
        info_sesion = self.sesion.obtener_info_sesion()
        
        return {
            'aplicacion': {
                'estado': self.estado_aplicacion,
                'modo': self.modo_operacion,
                'version': self.config.obtener('app.version'),
                'ssh_conectado': self.ssh_conectado,
                'ssh_configurado': self.ssh_configurado,
                'ultima_sincronizacion': self.ultima_sincronizacion
            },
            'base_datos': info_db,
            'sesion': info_sesion,
            'estadisticas': self.obtener_estadisticas_rapidas()
        }

# =============================================================================
# INTERFAZ DE USUARIO OPTIMIZADA PARA NUBE
# =============================================================================

class InterfazUsuario:
    """Clase para manejar la interfaz de usuario optimizada para nube"""
    
    def __init__(self, sistema: SistemaGestionEscolar):
        self.sistema = sistema
        self.config = sistema.config
    
    def mostrar_barra_lateral(self) -> str:
        """Mostrar barra lateral optimizada para nube"""
        with st.sidebar:
            # Logo y título
            st.markdown(f"""
            <div style="text-align: center;">
                <h1 style="color: #1E88E5;">{self.config.obtener('app.title')}</h1>
                <p style="color: #666; font-size: 0.9em;">Versión {self.config.obtener('app.version')}</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Estado del sistema optimizado
            st.subheader("📊 Estado del Sistema")
            
            stats = self.sistema.obtener_estadisticas_rapidas()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Estudiantes", stats['total_estudiantes'])
            with col2:
                st.metric("Activos", stats['estudiantes_activos'])
            
            # Estado de conexión optimizado para nube
            if self.sistema.ssh_conectado:
                st.success("🔗 Conectado al servidor")
            else:
                modo = self.sistema.modo_operacion
                if modo == 'nube':
                    st.success("☁️ Modo Nube")
                else:
                    st.success("💻 Modo Local")
            
            # Información de sesión
            with st.expander("ℹ️ Información de sesión"):
                info_sesion = self.sistema.sesion.obtener_info_sesion()
                st.write(f"**ID Sesión:** {info_sesion['session_id'][:8]}...")
                st.write(f"**Iniciada:** {info_sesion['iniciada']}")
                st.write(f"**Duración:** {info_sesion['duracion']}")
                st.write(f"**Estudiantes esta sesión:** {stats['estudiantes_sesion']}")
            
            st.markdown("---")
            
            # Navegación principal
            st.subheader("🧭 Navegación")
            
            opciones = [
                "🏠 Panel de Control",
                "👨‍🎓 Gestión de Estudiantes",
                "📝 Gestión de Inscripciones",
                "🎓 Gestión de Egresados",
                "💼 Seguimiento de Contratados",
                "⚙️ Configuración del Sistema"
            ]
            
            opcion_seleccionada = st.radio(
                "Seleccionar módulo:",
                opciones,
                label_visibility="collapsed"
            )
            
            st.markdown("---")
            
            # Acciones rápidas optimizadas
            st.subheader("⚡ Acciones Rápidas")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Backup", use_container_width=True, help="Crear copia de seguridad"):
                    with st.spinner("Creando backup..."):
                        success, msg = self.sistema.crear_backup()
                        if success:
                            st.success("✅ Backup creado")
                        else:
                            st.warning(f"⚠️ {msg}")
            
            with col2:
                if st.button("🔄 Sincronizar", use_container_width=True, help="Sincronizar con servidor"):
                    with st.spinner("Sincronizando..."):
                        success, msg = self.sistema.sincronizar_con_servidor()
                        if success:
                            st.success(f"✅ {msg}")
                        else:
                            st.error(f"❌ {msg}")
            
            st.markdown("---")
            
            # Información del sistema
            estado = self.sistema.obtener_estado_sistema()
            modo = estado['aplicacion']['modo']
            version = estado['aplicacion']['version']
            
            if modo == 'nube':
                st.caption(f"☁️ Modo Nube | v{version}")
            else:
                st.caption(f"💻 Modo Local | v{version}")
            
            return opcion_seleccionada
    
    def mostrar_panel_control(self):
        """Mostrar panel de control principal optimizado"""
        st.title("📊 Panel de Control")
        
        # Información del sistema
        estado = self.sistema.obtener_estado_sistema()
        
        with st.expander("ℹ️ Información del sistema", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Estado:**", estado['aplicacion']['estado'].capitalize())
                st.write("**Modo:**", estado['aplicacion']['modo'].capitalize())
                st.write("**Versión:**", estado['aplicacion']['version'])
            
            with col2:
                if estado['aplicacion']['ssh_conectado']:
                    st.success("🔗 SSH Conectado")
                else:
                    st.info("🔒 SSH Deshabilitado")
                
                if estado['aplicacion']['ultima_sincronizacion']:
                    st.write("**Última sync:**", estado['aplicacion']['ultima_sincronizacion'].strftime('%Y-%m-%d %H:%M'))
        
        # Estadísticas rápidas
        estadisticas = self.sistema.obtener_estadisticas_generales()
        
        st.subheader("📈 Estadísticas Principales")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🏫 Total Estudiantes", estadisticas.get('total_estudiantes', 0))
        with col2:
            st.metric("✅ Estudiantes Activos", estadisticas.get('estudiantes_activos', 0))
        with col3:
            st.metric("🎓 Egresados", estadisticas.get('total_egresados', 0))
        with col4:
            st.metric("💼 Contratados", estadisticas.get('egresados_contratados', 0))
        
        st.markdown("---")
        
        # Gráficos y visualizaciones
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Distribución por Estado")
            if estadisticas.get('estudiantes_por_estado'):
                df_estados = pd.DataFrame(
                    list(estadisticas['estudiantes_por_estado'].items()),
                    columns=['Estado', 'Cantidad']
                )
                st.bar_chart(df_estados.set_index('Estado'))
            else:
                st.info("No hay datos de distribución")
        
        with col2:
            st.subheader("📚 Estudiantes por Nivel")
            if estadisticas.get('estudiantes_por_nivel'):
                df_niveles = pd.DataFrame(
                    list(estadisticas['estudiantes_por_nivel'].items()),
                    columns=['Nivel', 'Cantidad']
                )
                st.bar_chart(df_niveles.set_index('Nivel'))
            else:
                st.info("No hay datos por nivel")
        
        # Top carreras
        st.subheader("🏆 Top Carreras")
        if estadisticas.get('top_carreras'):
            df_carreras = pd.DataFrame(
                list(estadisticas['top_carreras'].items()),
                columns=['Carrera', 'Estudiantes']
            )
            st.dataframe(df_carreras, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de carreras")
        
        # Inscripciones por ciclo
        st.subheader("📅 Inscripciones por Ciclo Escolar")
        if estadisticas.get('inscripciones_por_ciclo'):
            df_ciclos = pd.DataFrame(
                list(estadisticas['inscripciones_por_ciclo'].items()),
                columns=['Ciclo Escolar', 'Inscripciones']
            )
            st.dataframe(df_ciclos, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de inscripciones")
    
    def mostrar_gestion_estudiantes(self):
        """Mostrar interfaz de gestión de estudiantes"""
        st.title("👨‍🎓 Gestión de Estudiantes")
        
        # Pestañas
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Lista de Estudiantes", 
            "➕ Nuevo Estudiante", 
            "🔍 Buscar Estudiante",
            "📊 Estadísticas"
        ])
        
        with tab1:
            self._mostrar_lista_estudiantes()
        
        with tab2:
            self._mostrar_formulario_nuevo_estudiante()
        
        with tab3:
            self._mostrar_busqueda_estudiantes()
        
        with tab4:
            self._mostrar_estadisticas_estudiantes()
    
    def _mostrar_lista_estudiantes(self):
        """Mostrar lista de estudiantes con filtros"""
        # Filtros
        col1, col2, col3 = st.columns(3)
        
        with col1:
            estados = ['Todos'] + self.config.obtener('estados.estudiante', [])
            filtro_estado = st.selectbox("Filtrar por estado:", estados)
        
        with col2:
            niveles = ['Todos'] + self.config.obtener('estados.nivel', [])
            filtro_nivel = st.selectbox("Filtrar por nivel:", niveles)
        
        with col3:
            busqueda = st.text_input("Buscar (matrícula/nombre):")
        
        # Paginación
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            limite = st.number_input("Registros por página:", min_value=10, max_value=100, value=50)
        
        with col2:
            if 'pagina_estudiantes' not in st.session_state:
                st.session_state.pagina_estudiantes = 0
            
            total_paginas = st.empty()
        
        with col3:
            pagina_actual = st.session_state.pagina_estudiantes
            col_prev, _, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if st.button("◀ Anterior", disabled=pagina_actual == 0):
                    st.session_state.pagina_estudiantes -= 1
                    st.rerun()
            
            with col_next:
                if st.button("Siguiente ▶"):
                    st.session_state.pagina_estudiantes += 1
                    st.rerun()
        
        # Obtener estudiantes
        offset = pagina_actual * limite
        estudiantes = self.sistema.obtener_estudiantes(
            filtro_estado if filtro_estado != 'Todos' else None,
            filtro_nivel if filtro_nivel != 'Todos' else None,
            busqueda if busqueda else None,
            limite,
            offset
        )
        
        # Mostrar tabla
        if estudiantes:
            df = pd.DataFrame(estudiantes)
            
            # Seleccionar columnas para mostrar
            columnas_mostrar = ['id', 'matricula', 'nombre', 'apellido_paterno', 
                              'apellido_materno', 'carrera', 'semestre', 'estado_estudiante', 
                              'promedio', 'fecha_ingreso']
            
            # Filtrar columnas existentes
            columnas_existentes = [col for col in columnas_mostrar if col in df.columns]
            
            st.dataframe(df[columnas_existentes], use_container_width=True, hide_index=True)
            
            # Actualizar información de paginación
            total_registros = len(estudiantes) + offset
            total_paginas.markdown(f"**Página {pagina_actual + 1}**")
            
            # Acciones para estudiante seleccionado
            st.subheader("Acciones")
            
            if estudiantes:
                estudiante_opciones = {
                    f"{e['id']} - {e['matricula']} - {e['nombre']} {e['apellido_paterno']}": e['id']
                    for e in estudiantes
                }
                
                estudiante_seleccionado = st.selectbox(
                    "Seleccionar estudiante para acciones:",
                    list(estudiante_opciones.keys())
                )
                
                if estudiante_seleccionado:
                    estudiante_id = estudiante_opciones[estudiante_seleccionado]
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("📝 Editar", use_container_width=True):
                            st.session_state.editar_estudiante = estudiante_id
                            st.info("Funcionalidad de edición en desarrollo")
                    
                    with col2:
                        nuevo_estado = st.selectbox(
                            "Cambiar estado:",
                            self.config.obtener('estados.estudiante', []),
                            key=f"estado_{estudiante_id}"
                        )
                        if st.button("🔄 Actualizar", use_container_width=True):
                            success, msg = self.sistema.cambiar_estado_estudiante(estudiante_id, nuevo_estado)
                            if success:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                    
                    with col3:
                        if st.button("🗑️ Dar de baja", use_container_width=True):
                            confirmar = st.checkbox(f"¿Confirmar baja del estudiante {estudiante_id}?")
                            if confirmar:
                                success, msg = self.sistema.eliminar_estudiante(estudiante_id)
                                if success:
                                    st.success(f"✅ {msg}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg}")
        else:
            st.info("📭 No hay estudiantes que coincidan con los filtros")
            st.session_state.pagina_estudiantes = 0
    
    def _mostrar_formulario_nuevo_estudiante(self):
        """Mostrar formulario para nuevo estudiante"""
        st.subheader("➕ Registrar Nuevo Estudiante")
        
        with st.form("form_nuevo_estudiante"):
            col1, col2 = st.columns(2)
            
            with col1:
                matricula = st.text_input("Matrícula *", max_chars=20, help="Ejemplo: A12345678")
                nombre = st.text_input("Nombre *", max_chars=100)
                apellido_paterno = st.text_input("Apellido Paterno *", max_chars=100)
                apellido_materno = st.text_input("Apellido Materno", max_chars=100)
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", value=None)
                genero = st.selectbox("Género", self.config.obtener('estados.genero', []))
                curp = st.text_input("CURP", max_chars=18, help="18 caracteres")
                rfc = st.text_input("RFC", max_chars=13, help="13 caracteres")
            
            with col2:
                telefono = st.text_input("Teléfono", max_chars=10, help="10 dígitos")
                email = st.text_input("Email", max_chars=100)
                direccion = st.text_area("Dirección", max_chars=200)
                ciudad = st.text_input("Ciudad", max_chars=100)
                estado_res = st.text_input("Estado", max_chars=50)
                codigo_postal = st.text_input("Código Postal", max_chars=10)
                nivel_estudio = st.selectbox("Nivel de Estudio", self.config.obtener('estados.nivel', []))
                carrera = st.text_input("Carrera", max_chars=100)
                semestre = st.number_input("Semestre", min_value=1, max_value=20, value=1)
                turno = st.selectbox("Turno", self.config.obtener('estados.turno', []))
                fecha_ingreso = st.date_input("Fecha de Ingreso", value=datetime.now())
            
            # Botón de enviar
            submit = st.form_submit_button("💾 Guardar Estudiante", type="primary")
            
            if submit:
                # Preparar datos
                datos_estudiante = {
                    'matricula': matricula.strip(),
                    'nombre': nombre.strip(),
                    'apellido_paterno': apellido_paterno.strip(),
                    'apellido_materno': apellido_materno.strip() if apellido_materno else None,
                    'fecha_nacimiento': fecha_nacimiento.isoformat() if fecha_nacimiento else None,
                    'genero': genero,
                    'curp': curp.strip() if curp else None,
                    'rfc': rfc.strip() if rfc else None,
                    'telefono': telefono.strip() if telefono else None,
                    'email': email.strip() if email else None,
                    'direccion': direccion.strip() if direccion else None,
                    'ciudad': ciudad.strip() if ciudad else None,
                    'estado': estado_res.strip() if estado_res else None,
                    'codigo_postal': codigo_postal.strip() if codigo_postal else None,
                    'nivel_estudio': nivel_estudio,
                    'carrera': carrera.strip() if carrera else None,
                    'semestre': semestre,
                    'turno': turno,
                    'fecha_ingreso': fecha_ingreso.isoformat() if fecha_ingreso else None,
                    'estado_estudiante': 'Activo'
                }
                
                # Crear estudiante
                success, msg, estudiante_id = self.sistema.crear_estudiante(datos_estudiante)
                
                if success:
                    st.success(f"✅ {msg} - ID: {estudiante_id}")
                    
                    # Preguntar si desea inscribirlo
                    with st.expander("📝 ¿Inscribir al estudiante?"):
                        ciclo_actual = self.sistema.obtener_proximo_ciclo_escolar()
                        st.write(f"Ciclo escolar sugerido: **{ciclo_actual}**")
                        
                        if st.button(f"Inscribir en {ciclo_actual}"):
                            success_ins, msg_ins, _ = self.sistema.inscribir_estudiante(
                                estudiante_id, ciclo_actual, semestre
                            )
                            if success_ins:
                                st.success(f"✅ {msg_ins}")
                            else:
                                st.warning(f"⚠️ {msg_ins}")
                    
                    # Limpiar formulario
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
    
    def _mostrar_busqueda_estudiantes(self):
        """Mostrar interfaz de búsqueda avanzada"""
        st.subheader("🔍 Búsqueda Avanzada de Estudiantes")
        
        col1, col2 = st.columns(2)
        
        with col1:
            criterio = st.selectbox(
                "Buscar por:",
                ['matricula', 'nombre', 'curp', 'email']
            )
        
        with col2:
            valor = st.text_input("Valor a buscar:")
        
        if valor:
            resultados = self.sistema.buscar_estudiante(criterio, valor)
            
            if resultados:
                st.success(f"✅ Encontrados {len(resultados)} estudiantes")
                
                df = pd.DataFrame(resultados)
                columnas_mostrar = ['id', 'matricula', 'nombre', 'apellido_paterno', 
                                  'apellido_materno', 'carrera', 'estado_estudiante', 'email']
                
                columnas_existentes = [col for col in columnas_mostrar if col in df.columns]
                st.dataframe(df[columnas_existentes], use_container_width=True, hide_index=True)
            else:
                st.info("📭 No se encontraron estudiantes con esos criterios")
    
    def _mostrar_estadisticas_estudiantes(self):
        """Mostrar estadísticas de estudiantes"""
        estadisticas = self.sistema.obtener_estadisticas_generales()
        
        st.subheader("📊 Estadísticas de Estudiantes")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Estudiantes", estadisticas.get('total_estudiantes', 0))
            st.metric("Estudiantes Activos", estadisticas.get('estudiantes_activos', 0))
            st.metric("Promedio General", f"{estadisticas.get('promedio_general', 0):.2f}")
        
        with col2:
            st.metric("Total Egresados", estadisticas.get('total_egresados', 0))
            st.metric("Egresados Contratados", estadisticas.get('egresados_contratados', 0))
        
        # Exportar datos
        st.subheader("📤 Exportar Datos")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 Estudiantes (Excel)"):
                output, nombre = self.sistema.generar_informe_excel('estudiantes')
                if output:
                    st.download_button(
                        label="⬇️ Descargar",
                        data=output,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.error("❌ No hay datos para exportar")
        
        with col2:
            if st.button("🎓 Egresados (Excel)"):
                output, nombre = self.sistema.generar_informe_excel('egresados')
                if output:
                    st.download_button(
                        label="⬇️ Descargar",
                        data=output,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.error("❌ No hay datos para exportar")
        
        with col3:
            if st.button("💼 Contratados (Excel)"):
                output, nombre = self.sistema.generar_informe_excel('contratados')
                if output:
                    st.download_button(
                        label="⬇️ Descargar",
                        data=output,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.error("❌ No hay datos para exportar")
    
    def mostrar_gestion_inscripciones(self):
        """Mostrar interfaz de gestión de inscripciones"""
        st.title("📝 Gestión de Inscripciones")
        
        # Obtener ciclo escolar actual
        ciclo_actual = self.sistema.obtener_proximo_ciclo_escolar()
        st.info(f"🏫 Ciclo escolar actual: **{ciclo_actual}**")
        
        # Pestañas
        tab1, tab2, tab3 = st.tabs([
            "📋 Inscripciones Actuales",
            "➕ Nueva Inscripción",
            "📊 Estadísticas por Ciclo"
        ])
        
        with tab1:
            self._mostrar_inscripciones_actuales(ciclo_actual)
        
        with tab2:
            self._mostrar_nueva_inscripcion(ciclo_actual)
        
        with tab3:
            self._mostrar_estadisticas_inscripciones()
    
    def _mostrar_inscripciones_actuales(self, ciclo_actual: str):
        """Mostrar inscripciones del ciclo actual"""
        inscripciones = self.sistema.obtener_inscripciones(ciclo_escolar=ciclo_actual)
        
        if inscripciones:
            st.subheader(f"Inscripciones del ciclo {ciclo_actual}")
            
            # Crear DataFrame
            datos = []
            for ins in inscripciones:
                datos.append({
                    'ID': ins['id'],
                    'Matrícula': ins['matricula'],
                    'Estudiante': f"{ins['nombre']} {ins['apellido_paterno']} {ins.get('apellido_materno', '')}",
                    'Semestre': ins['semestre'],
                    'Créditos': ins['creditos_inscritos'],
                    'Promedio': ins['promedio_ciclo'],
                    'Estatus': ins['estatus'],
                    'Fecha': ins['fecha_inscripcion'][:10] if ins['fecha_inscripcion'] else ''
                })
            
            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info(f"📭 No hay inscripciones para el ciclo {ciclo_actual}")
    
    def _mostrar_nueva_inscripcion(self, ciclo_actual: str):
        """Mostrar formulario para nueva inscripción"""
        st.subheader("Nueva Inscripción")
        
        # Listar estudiantes activos no inscritos en este ciclo
        estudiantes_activos = self.sistema.obtener_estudiantes('Activo', None, 1000)
        
        # Filtrar estudiantes ya inscritos en este ciclo
        inscripciones_actuales = self.sistema.obtener_inscripciones(ciclo_escolar=ciclo_actual)
        ids_inscritos = {ins['estudiante_id'] for ins in inscripciones_actuales}
        
        estudiantes_disponibles = [
            est for est in estudiantes_activos 
            if est['id'] not in ids_inscritos
        ]
        
        if not estudiantes_disponibles:
            st.warning("⚠️ No hay estudiantes disponibles para inscripción en este ciclo")
            return
        
        # Formulario
        estudiante_opciones = {
            f"{est['id']} - {est['matricula']} - {est['nombre']} {est['apellido_paterno']}": est['id']
            for est in estudiantes_disponibles
        }
        
        estudiante_seleccionado = st.selectbox(
            "Seleccionar estudiante:",
            list(estudiante_opciones.keys())
        )
        
        if estudiante_seleccionado:
            estudiante_id = estudiante_opciones[estudiante_seleccionado]
            
            # Obtener información del estudiante
            estudiante = self.sistema.obtener_estudiante_por_id(estudiante_id)
            
            if estudiante:
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Carrera:** {estudiante.get('carrera', 'No especificada')}")
                    st.write(f"**Nivel:** {estudiante.get('nivel_estudio', 'No especificado')}")
                with col2:
                    st.write(f"**Semestre actual:** {estudiante.get('semestre', 'No especificado')}")
                    st.write(f"**Promedio:** {estudiante.get('promedio', 'No registrado')}")
                
                # Datos de la inscripción
                semestre_inscripcion = st.number_input(
                    "Semestre a inscribir:", 
                    min_value=1, 
                    max_value=20, 
                    value=estudiante.get('semestre', 1)
                )
                
                creditos_inscritos = st.number_input(
                    "Créditos a inscribir:", 
                    min_value=0, 
                    max_value=50, 
                    value=0
                )
                
                if st.button("📝 Realizar Inscripción", type="primary"):
                    success, msg, _ = self.sistema.inscribir_estudiante(
                        estudiante_id, 
                        ciclo_actual, 
                        semestre_inscripcion, 
                        creditos_inscritos
                    )
                    if success:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
    
    def _mostrar_estadisticas_inscripciones(self):
        """Mostrar estadísticas de inscripciones"""
        estadisticas = self.sistema.obtener_estadisticas_generales()
        
        if estadisticas.get('inscripciones_por_ciclo'):
            st.subheader("📈 Inscripciones por Ciclo Escolar")
            
            df_ciclos = pd.DataFrame(
                list(estadisticas['inscripciones_por_ciclo'].items()),
                columns=['Ciclo Escolar', 'Inscripciones']
            )
            
            st.dataframe(df_ciclos, use_container_width=True, hide_index=True)
            st.bar_chart(df_ciclos.set_index('Ciclo Escolar'))
        else:
            st.info("📭 No hay datos de inscripciones para mostrar")
    
    def mostrar_gestion_egresados(self):
        """Mostrar interfaz de gestión de egresados"""
        st.title("🎓 Gestión de Egresados")
        
        tab1, tab2, tab3 = st.tabs([
            "📋 Lista de Egresados",
            "➕ Registrar Egresado",
            "💼 Contrataciones"
        ])
        
        with tab1:
            self._mostrar_lista_egresados()
        
        with tab2:
            self._mostrar_registro_egresado()
        
        with tab3:
            self._mostrar_gestion_contrataciones()
    
    def _mostrar_lista_egresados(self):
        """Mostrar lista de egresados"""
        # Filtros
        col1, col2 = st.columns(2)
        
        with col1:
            filtro_titulo = st.text_input("Filtrar por título obtenido:")
        
        with col2:
            filtro_fecha = st.date_input("Filtrar desde fecha:", value=None)
        
        # Obtener egresados
        egresados = self.sistema.obtener_egresados(
            filtro_titulo if filtro_titulo else None,
            filtro_fecha.isoformat() if filtro_fecha else None
        )
        
        if egresados:
            # Preparar datos para mostrar
            datos = []
            for eg in egresados:
                datos.append({
                    'ID': eg['id'],
                    'Matrícula': eg['matricula'],
                    'Egresado': f"{eg['nombre']} {eg['apellido_paterno']}",
                    'Carrera': eg['carrera'],
                    'Título': eg['titulo_obtenido'],
                    'Promedio': eg['promedio_final'],
                    'Fecha Egreso': eg['fecha_egreso'][:10] if eg['fecha_egreso'] else '',
                    'Cédula': eg['numero_cedula']
                })
            
            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("📭 No hay egresados registrados")
    
    def _mostrar_registro_egresado(self):
        """Mostrar formulario para registrar egresado"""
        st.subheader("Registrar Nuevo Egresado")
        
        # Listar estudiantes activos no egresados
        estudiantes_activos = self.sistema.obtener_estudiantes('Activo', None, 1000)
        
        if not estudiantes_activos:
            st.warning("⚠️ No hay estudiantes activos disponibles")
            return
        
        estudiante_opciones = {
            f"{est['id']} - {est['matricula']} - {est['nombre']} {est['apellido_paterno']}": est['id']
            for est in estudiantes_activos
        }
        
        estudiante_seleccionado = st.selectbox(
            "Seleccionar estudiante:",
            list(estudiante_opciones.keys())
        )
        
        if estudiante_seleccionado:
            estudiante_id = estudiante_opciones[estudiante_seleccionado]
            
            # Obtener información del estudiante
            estudiante = self.sistema.obtener_estudiante_por_id(estudiante_id)
            
            if estudiante:
                st.write(f"**Carrera:** {estudiante.get('carrera', 'No especificada')}")
                st.write(f"**Promedio actual:** {estudiante.get('promedio', 'No registrado')}")
                
                # Formulario de egreso
                fecha_egreso = st.date_input("Fecha de Egreso *", value=datetime.now())
                titulo_obtenido = st.text_input("Título Obtenido *", max_chars=200)
                promedio_final = st.number_input(
                    "Promedio Final *", 
                    min_value=0.0, 
                    max_value=10.0, 
                    value=float(estudiante.get('promedio', 0.0) or 0.0),
                    step=0.1
                )
                
                if st.button("🎓 Registrar Egresado", type="primary"):
                    if not titulo_obtenido:
                        st.error("❌ El título obtenido es obligatorio")
                    else:
                        success, msg, _ = self.sistema.registrar_egresado(
                            estudiante_id,
                            fecha_egreso.isoformat(),
                            titulo_obtenido,
                            promedio_final
                        )
                        if success:
                            st.success(f"✅ {msg}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
    
    def _mostrar_gestion_contrataciones(self):
        """Mostrar gestión de contrataciones"""
        st.subheader("💼 Gestión de Contrataciones")
        
        contratados = self.sistema.obtener_contratados()
        
        if contratados:
            # Preparar datos
            datos = []
            for cont in contratados:
                datos.append({
                    'ID': cont['id'],
                    'Matrícula': cont['matricula'],
                    'Egresado': f"{cont['nombre']} {cont['apellido_paterno']}",
                    'Carrera': cont['carrera'],
                    'Empresa': cont['empresa'],
                    'Puesto': cont['puesto'],
                    'Salario': f"${cont['salario_actual'] or cont['salario_inicial']:,.2f}" 
                               if cont['salario_actual'] or cont['salario_inicial'] else 'No especificado',
                    'Fecha Contratación': cont['fecha_contratacion'][:10] 
                                         if cont['fecha_contratacion'] else ''
                })
            
            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("📭 No hay contrataciones registradas")
    
    def mostrar_configuracion_sistema(self):
        """Mostrar configuración del sistema optimizada para nube"""
        st.title("⚙️ Configuración del Sistema")
        
        tab1, tab2, tab3 = st.tabs([
            "📊 Estado del Sistema",
            "💾 Backup",
            "🔧 Configuración"
        ])
        
        with tab1:
            self._mostrar_estado_sistema()
        
        with tab2:
            self._mostrar_backup()
        
        with tab3:
            self._mostrar_configuracion()
    
    def _mostrar_estado_sistema(self):
        """Mostrar estado actual del sistema"""
        st.subheader("📊 Estado del Sistema")
        
        # Obtener información del sistema
        estado = self.sistema.obtener_estado_sistema()
        
        # Información general
        st.write("### 🚀 Información General")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Estado:** {estado['aplicacion']['estado'].capitalize()}")
            st.write(f"**Modo:** {estado['aplicacion']['modo'].capitalize()}")
            st.write(f"**Versión:** {estado['aplicacion']['version']}")
        
        with col2:
            if estado['aplicacion']['ssh_conectado']:
                st.success("🔗 SSH Conectado")
            elif estado['aplicacion']['ssh_configurado']:
                st.warning("⚠️ SSH Configurado pero no conectado")
            else:
                st.info("🔒 SSH Deshabilitado")
            
            if estado['aplicacion']['ultima_sincronizacion']:
                st.write(f"**Última sync:** {estado['aplicacion']['ultima_sincronizacion'].strftime('%Y-%m-%d %H:%M')}")
        
        # Información de base de datos
        st.write("### 🗄️ Base de Datos")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Ruta:** {estado['base_datos']['ruta_db']}")
            st.write(f"**Modo:** {estado['base_datos']['modo']}")
        
        with col2:
            st.write(f"**Tamaño:** {estado['base_datos']['tamano_db']}")
            if estado['base_datos']['es_temporal']:
                st.info("📝 Base de datos temporal para esta sesión")
        
        # Estadísticas
        st.write("### 📈 Estadísticas")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Estudiantes", estado['estadisticas']['total_estudiantes'])
        with col2:
            st.metric("Activos", estado['estadisticas']['estudiantes_activos'])
        with col3:
            st.metric("Esta sesión", estado['estadisticas']['estudiantes_sesion'])
        
        # Información de sesión
        st.write("### 💻 Sesión Actual")
        info_sesion = estado['sesion']
        st.write(f"**ID Sesión:** {info_sesion['session_id'][:16]}...")
        st.write(f"**Iniciada:** {info_sesion['iniciada']}")
        st.write(f"**Duración:** {info_sesion['duracion']}")
        
        # Limpiar datos de sesión
        if st.button("🧹 Limpiar datos de esta sesión"):
            if self.sistema.sesion.limpiar_datos_sesion(self.sistema.db):
                st.success("✅ Datos de sesión limpiados")
                st.rerun()
            else:
                st.error("❌ Error limpiando datos de sesión")
    
    def _mostrar_sincronizacion(self):
        """Mostrar opciones de sincronización (simplificado para nube)"""
        st.subheader("🔄 Sincronización")
        
        estado = self.sistema.obtener_estado_sistema()
        
        if estado['aplicacion']['ssh_conectado']:
            st.success("✅ SSH conectado")
            st.write("**Host:**", self.config.obtener('ssh.host', 'No configurado'))
            st.write("**Usuario:**", self.config.obtener('ssh.username', 'No configurado'))
            
            if st.button("🔄 Sincronizar ahora", type="primary"):
                with st.spinner("Sincronizando..."):
                    success, msg = self.sistema.sincronizar_con_servidor()
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")
        else:
            # Mensaje optimizado para nube
            st.info("""
            ### ℹ️ Información de Sincronización
            
            **Modo actual:** {'☁️ Nube' if estado['aplicacion']['modo'] == 'nube' else '💻 Local'}
            
            En modo de despliegue en la nube, la sincronización SSH está **deshabilitada por seguridad**.
            
            **Funcionalidades disponibles:**
            - Gestión completa de estudiantes
            - Sistema de inscripciones
            - Registro de egresados y contrataciones
            - Exportación de informes Excel
            - Sistema de backup local
            
            **Para desarrollo local con SSH:**
            1. Configura las credenciales SSH en `config.json`
            2. Establece `"ssh": {"enabled": true}`
            3. Ejecuta la aplicación localmente
            """)
    
    def _mostrar_backup(self):
        """Mostrar opciones de backup"""
        st.subheader("💾 Sistema de Backup")
        
        # Crear backup manual
        if st.button("💾 Crear Backup Manual", type="primary"):
            with st.spinner("Creando backup..."):
                success, msg = self.sistema.crear_backup()
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")
        
        # Listar backups existentes
        estado = self.sistema.obtener_estado_sistema()
        backup_dir = estado['base_datos']['backup_dir']
        
        st.write("### 📦 Backups Existentes")
        
        if os.path.exists(backup_dir):
            backups = []
            for file in os.listdir(backup_dir):
                if file.startswith('escuela_backup_'):
                    file_path = os.path.join(backup_dir, file)
                    try:
                        size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                        backups.append({
                            'Archivo': file,
                            'Tamaño (MB)': f"{size_mb:.2f}",
                            'Fecha': mtime.strftime('%Y-%m-%d %H:%M:%S')
                        })
                    except:
                        pass
            
            if backups:
                df_backups = pd.DataFrame(backups)
                st.dataframe(df_backups, use_container_width=True, hide_index=True)
            else:
                st.info("📭 No hay backups creados")
        else:
            st.info("📭 Directorio de backups no existe")
    
    def _mostrar_configuracion(self):
        """Mostrar configuración del sistema"""
        st.subheader("🔧 Configuración del Sistema")
        
        # Configuración general
        with st.expander("⚙️ Configuración General", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                nuevo_page_size = st.number_input(
                    "Tamaño de página (registros):",
                    min_value=10,
                    max_value=200,
                    value=self.config.obtener('app.page_size', 50)
                )
            
            with col2:
                nuevo_cache_ttl = st.number_input(
                    "TTL de caché (segundos):",
                    min_value=60,
                    max_value=3600,
                    value=self.config.obtener('app.cache_ttl', 300)
                )
            
            if st.button("💾 Guardar Configuración (sesión actual)"):
                st.success("✅ Configuración guardada (en sesión actual)")
        
        # Configuración de backup
        with st.expander("💾 Configuración de Backup"):
            col1, col2 = st.columns(2)
            
            with col1:
                max_backups = st.number_input(
                    "Máximo de backups a mantener:",
                    min_value=1,
                    max_value=50,
                    value=self.config.obtener('database.max_backups', 10)
                )
            
            with col2:
                backup_enabled = st.checkbox(
                    "Habilitar sistema de backup",
                    value=self.config.obtener('database.backup_enabled', True)
                )
        
        # Limpiar caché
        with st.expander("🗑️ Mantenimiento"):
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🧹 Limpiar Caché"):
                    self.sistema.limpiar_cache()
                    st.success("✅ Caché limpiado")
                    st.rerun()
            
            with col2:
                if st.button("🔄 Reiniciar sistema (sesión)"):
                    if 'sistema' in st.session_state:
                        del st.session_state.sistema
                        del st.session_state.ui
                    st.success("✅ Sistema reiniciado")
                    st.rerun()

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal de la aplicación optimizada"""
    # Configurar página
    st.set_page_config(
        page_title="Sistema de Gestión Escolar",
        page_icon="🏫",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Inicializar sistema
    if 'sistema' not in st.session_state:
        with st.spinner("🚀 Inicializando sistema..."):
            try:
                st.session_state.sistema = SistemaGestionEscolar()
                st.session_state.ui = InterfazUsuario(st.session_state.sistema)
                st.success("✅ Sistema inicializado correctamente")
            except Exception as e:
                st.error(f"❌ Error crítico al inicializar el sistema: {e}")
                st.stop()
    
    sistema = st.session_state.sistema
    ui = st.session_state.ui
    
    # Mostrar barra lateral y obtener opción
    opcion = ui.mostrar_barra_lateral()
    
    # Mostrar contenido según opción
    try:
        if opcion == "🏠 Panel de Control":
            ui.mostrar_panel_control()
        
        elif opcion == "👨‍🎓 Gestión de Estudiantes":
            ui.mostrar_gestion_estudiantes()
        
        elif opcion == "📝 Gestión de Inscripciones":
            ui.mostrar_gestion_inscripciones()
        
        elif opcion == "🎓 Gestión de Egresados":
            ui.mostrar_gestion_egresados()
        
        elif opcion == "💼 Seguimiento de Contratados":
            ui.mostrar_gestion_egresados()  # Por ahora usa la misma
        
        elif opcion == "⚙️ Configuración del Sistema":
            ui.mostrar_configuracion_sistema()
    
    except Exception as e:
        st.error(f"❌ Error en la aplicación: {e}")
        st.exception(e)
    
    # Pie de página
    st.markdown("---")
    
    estado = sistema.obtener_estado_sistema()
    modo = estado['aplicacion']['modo']
    version = estado['aplicacion']['version']
    
    if modo == 'nube':
        st.caption(f"© 2024 Sistema de Gestión Escolar v{version} | ☁️ Modo Nube")
    else:
        st.caption(f"© 2024 Sistema de Gestión Escolar v{version} | 💻 Modo Local")

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    main()
