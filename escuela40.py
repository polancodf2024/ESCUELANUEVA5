"""
escuela40.py - Sistema de Gestión de Escuela (Versión 4.0 Corregida)
Sistema COMPLETO y CORREGIDO para despliegue en Streamlit Cloud
Versión optimizada con manejo de conexión SSH y mensajes mejorados
CONECTADO AL SERVIDOR REMOTO VIA SECRETS.TOML
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
import paramiko
import socket

warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURACIÓN DEL SISTEMA - MODIFICADA PARA USAR SECRETS.TOML
# =============================================================================

class ConfiguracionSistema:
    """Gestión centralizada de configuración con soporte para secrets.toml"""
    
    _instancia = None
    
    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializar()
        return cls._instancia
    
    def _inicializar(self):
        """Inicializar configuración desde secrets.toml"""
        # Configuración por defecto
        self.config = {
            'app': {
                'title': '🏫 Sistema de Gestión Escolar',
                'version': '4.0',
                'icon': '🏫',
                'page_size': 50,
                'cache_ttl': 300,
                'modo': 'nube'
            },
            'database': {
                'name': 'escuela.db',
                'backup_dir': 'backups',
                'max_backups': 10,
                'backup_enabled': True,
                'temporal': True
            },
            'ssh': {
                'enabled': False,  # Se sobreescribirá desde secrets.toml
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
        
        # Cargar configuración desde secrets.toml (PRIORIDAD MÁXIMA)
        self._cargar_secrets_toml()
    
    def _cargar_secrets_toml(self):
        """Cargar configuración desde secrets.toml de Streamlit Cloud"""
        try:
            # Método 1: Usar st.secrets (Streamlit Cloud)
            if hasattr(st, 'secrets') and st.secrets:
                secrets = st.secrets
                
                # Cargar configuración SSH desde secrets.toml
                if 'smtp' in secrets:
                    self.config['smtp'] = dict(secrets['smtp'])
                
                if 'ssh' in secrets:
                    ssh_config = dict(secrets['ssh'])
                    # Habilitar SSH si está configurado en secrets.toml
                    if ssh_config.get('enabled', True):  # Por defecto True si existe
                        self.config['ssh'].update({
                            'enabled': True,
                            'host': ssh_config.get('host', ''),
                            'port': ssh_config.get('port', 22),
                            'username': ssh_config.get('username', ''),
                            'password': ssh_config.get('password', ''),
                            'timeout': ssh_config.get('timeout', 30)
                        })
                        print("✅ SSH habilitado desde secrets.toml")
                
                if 'remote_paths' in secrets:
                    self.config['remote_paths'] = dict(secrets['remote_paths'])
                
                if 'system' in secrets:
                    system_config = dict(secrets['system'])
                    self.config['system'] = {
                        'supervisor_mode': system_config.get('supervisor_mode', False),
                        'debug_mode': system_config.get('debug_mode', False)
                    }
                
                print("✅ Configuración cargada desde st.secrets")
                
            # Método 2: Cargar desde archivo local secrets.toml
            elif os.path.exists('secrets.toml'):
                try:
                    import tomli
                    with open('secrets.toml', 'r', encoding='utf-8') as f:
                        secrets = tomli.load(f)
                    
                    # Cargar configuración SSH
                    if 'ssh' in secrets and secrets['ssh'].get('enabled', True):
                        self.config['ssh'].update({
                            'enabled': True,
                            'host': secrets['ssh'].get('host', ''),
                            'port': secrets['ssh'].get('port', 22),
                            'username': secrets['ssh'].get('username', ''),
                            'password': secrets['ssh'].get('password', ''),
                            'timeout': secrets['ssh'].get('timeout', 30)
                        })
                        print("✅ SSH habilitado desde archivo secrets.toml local")
                except ImportError:
                    import tomllib
                    with open('secrets.toml', 'r', encoding='utf-8') as f:
                        secrets = tomllib.load(f)
                    
                    # Cargar configuración SSH
                    if 'ssh' in secrets and secrets['ssh'].get('enabled', True):
                        self.config['ssh'].update({
                            'enabled': True,
                            'host': secrets['ssh'].get('host', ''),
                            'port': secrets['ssh'].get('port', 22),
                            'username': secrets['ssh'].get('username', ''),
                            'password': secrets['ssh'].get('password', ''),
                            'timeout': secrets['ssh'].get('timeout', 30)
                        })
                        print("✅ SSH habilitado desde archivo secrets.toml local")
            
            # Método 3: Cargar desde variables de entorno (Streamlit Cloud)
            else:
                # Intentar cargar desde variables de entorno
                ssh_host = os.environ.get('SSH_HOST')
                ssh_user = os.environ.get('SSH_USERNAME')
                ssh_pass = os.environ.get('SSH_PASSWORD')
                
                if ssh_host and ssh_user and ssh_pass:
                    self.config['ssh'].update({
                        'enabled': True,
                        'host': ssh_host,
                        'username': ssh_user,
                        'password': ssh_pass,
                        'port': int(os.environ.get('SSH_PORT', '3792')),
                        'timeout': int(os.environ.get('SSH_TIMEOUT', '30'))
                    })
                    print("✅ SSH habilitado desde variables de entorno")
                    
        except Exception as e:
            print(f"⚠️ Error cargando secrets.toml: {e}")
            # Continuar con valores por defecto
    
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
        """Establecer valor de configuración"""
        keys = clave.split('.')
        current = self.config
        
        for i, key in enumerate(keys[:-1]):
            if key not in current or not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = valor

# =============================================================================
# GESTIÓN DE CONEXIÓN SSH MEJORADA
# =============================================================================

class GestorSSH:
    """Gestor mejorado de conexión SSH al servidor remoto"""
    
    def __init__(self, config: ConfiguracionSistema):
        self.config = config
        self.ssh_client = None
        self.sftp = None
        self.conectado = False
        self.ultima_conexion = None
        self.error_conexion = None
        
    def conectar(self) -> Tuple[bool, str]:
        """Conectar al servidor SSH remoto"""
        try:
            # Verificar si SSH está habilitado
            if not self.config.obtener('ssh.enabled', False):
                return False, "SSH no está habilitado en la configuración"
            
            # Obtener credenciales
            host = self.config.obtener('ssh.host', '')
            username = self.config.obtener('ssh.username', '')
            password = self.config.obtener('ssh.password', '')
            port = self.config.obtener('ssh.port', 22)
            timeout = self.config.obtener('ssh.timeout', 30)
            
            if not host or not username or not password:
                return False, "Credenciales SSH incompletas"
            
            print(f"🔗 Intentando conexión SSH a {host}:{port} como {username}...")
            
            # Crear cliente SSH
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Configurar timeout
            socket.setdefaulttimeout(timeout)
            
            # Conectar
            self.ssh_client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Abrir canal SFTP
            self.sftp = self.ssh_client.open_sftp()
            
            self.conectado = True
            self.ultima_conexion = datetime.now()
            self.error_conexion = None
            
            print(f"✅ Conexión SSH establecida a {host}")
            return True, f"Conexión exitosa a {host}"
            
        except socket.timeout:
            error_msg = f"Timeout al conectar a {host}:{port}"
            self.error_conexion = error_msg
            return False, error_msg
            
        except paramiko.AuthenticationException:
            error_msg = "Error de autenticación. Verifique usuario/contraseña."
            self.error_conexion = error_msg
            return False, error_msg
            
        except paramiko.SSHException as e:
            error_msg = f"Error SSH: {str(e)}"
            self.error_conexion = error_msg
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Error inesperado: {str(e)}"
            self.error_conexion = error_msg
            return False, error_msg
    
    def desconectar(self):
        """Desconectar del servidor SSH"""
        try:
            if self.sftp:
                self.sftp.close()
            if self.ssh_client:
                self.ssh_client.close()
        except:
            pass
        finally:
            self.ssh_client = None
            self.sftp = None
            self.conectado = False
    
    def ejecutar_comando(self, comando: str) -> Tuple[bool, str]:
        """Ejecutar comando remoto en el servidor"""
        if not self.conectado or not self.ssh_client:
            return False, "No conectado al servidor SSH"
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(comando, timeout=30)
            salida = stdout.read().decode('utf-8', errors='ignore')
            error = stderr.read().decode('utf-8', errors='ignore')
            
            if error and not salida:
                return False, f"Error: {error}"
            
            return True, salida if salida else "Comando ejecutado exitosamente"
            
        except Exception as e:
            return False, f"Error ejecutando comando: {str(e)}"
    
    def subir_archivo(self, local_path: str, remote_path: str) -> Tuple[bool, str]:
        """Subir archivo al servidor remoto"""
        if not self.conectado or not self.sftp:
            return False, "No conectado al servidor SSH"
        
        try:
            self.sftp.put(local_path, remote_path)
            return True, f"Archivo subido exitosamente a {remote_path}"
        except Exception as e:
            return False, f"Error subiendo archivo: {str(e)}"
    
    def descargar_archivo(self, remote_path: str, local_path: str) -> Tuple[bool, str]:
        """Descargar archivo del servidor remoto"""
        if not self.conectado or not self.sftp:
            return False, "No conectado al servidor SSH"
        
        try:
            self.sftp.get(remote_path, local_path)
            return True, f"Archivo descargado exitosamente a {local_path}"
        except Exception as e:
            return False, f"Error descargando archivo: {str(e)}"
    
    def listar_directorio(self, remote_path: str) -> Tuple[bool, List[str]]:
        """Listar contenido de directorio remoto"""
        if not self.conectado or not self.sftp:
            return False, []
        
        try:
            archivos = self.sftp.listdir(remote_path)
            return True, archivos
        except:
            return False, []
    
    def obtener_estado(self) -> Dict[str, Any]:
        """Obtener estado de la conexión SSH"""
        return {
            'conectado': self.conectado,
            'ultima_conexion': self.ultima_conexion,
            'error_conexion': self.error_conexion,
            'host': self.config.obtener('ssh.host', ''),
            'username': self.config.obtener('ssh.username', ''),
            'port': self.config.obtener('ssh.port', 22)
        }

# =============================================================================
# GESTIÓN DE BASE DE DATOS SIMPLIFICADA (SIN COLUMNA SINCRONIZADO)
# =============================================================================

class GestorBaseDatos:
    """Gestor de base de datos simplificado para compatibilidad"""
    
    def __init__(self, config: ConfiguracionSistema, gestor_ssh: GestorSSH = None):
        self.config = config
        self.gestor_ssh = gestor_ssh
        self._inicializar_rutas()
        self._inicializar_db()
    
    def _inicializar_rutas(self):
        """Inicializar rutas locales"""
        # Directorio base
        base_dir = '.'
        self.base_dir = base_dir
        self.db_path = os.path.join(base_dir, self.config.obtener('database.name', 'escuela.db'))
        self.backup_dir = os.path.join(base_dir, self.config.obtener('database.backup_dir', 'backups'))
        
        # Crear directorios locales
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(os.path.join(base_dir, 'uploads'), exist_ok=True)
        os.makedirs(os.path.join(base_dir, 'logs'), exist_ok=True)
    
    def _inicializar_db(self):
        """Inicializar estructura de la base de datos (COMPATIBLE con versión anterior)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de estudiantes (MANTENER estructura original)
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
            
            # Índices
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_matricula ON estudiantes(matricula)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_nombre ON estudiantes(nombre, apellido_paterno)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_estado ON estudiantes(estado_estudiante)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_est_email ON estudiantes(email)')
            
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
            
            # Insertar usuario administrador por defecto
            cursor.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
            if cursor.fetchone()[0] == 0:
                password_hash = hashlib.sha256('Admin@Nube2024!'.encode()).hexdigest()
                cursor.execute(
                    """INSERT INTO usuarios 
                       (username, password_hash, nombre_completo, email, rol) 
                       VALUES (?, ?, ?, ?, ?)""",
                    ('admin', password_hash, 'Administrador del Sistema', 
                     'admin@escuela.edu.mx', 'admin')
                )
            
            conn.commit()
            print("✅ Base de datos inicializada correctamente")
    
    @contextmanager
    def _get_connection(self):
        """Context manager para conexiones a BD"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        
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
    
    def descargar_db_remota(self) -> Tuple[bool, str]:
        """Descargar base de datos remota si hay conexión SSH"""
        if not self.gestor_ssh or not self.gestor_ssh.conectado:
            return False, "No conectado al servidor SSH"
        
        try:
            # Obtener ruta remota desde configuración
            ruta_remota = self.config.obtener('remote_paths.escuela_db', '')
            if not ruta_remota:
                return False, "Ruta remota no configurada"
            
            # Crear backup de la base de datos local actual
            backup_path = f"{self.db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if os.path.exists(self.db_path):
                shutil.copy2(self.db_path, backup_path)
            
            # Descargar base de datos remota
            success, msg = self.gestor_ssh.descargar_archivo(ruta_remota, self.db_path)
            
            if success:
                # Verificar que el archivo descargado sea una base de datos válida
                try:
                    test_conn = sqlite3.connect(self.db_path)
                    test_conn.execute("SELECT 1 FROM sqlite_master LIMIT 1")
                    test_conn.close()
                    return True, "Base de datos remota descargada exitosamente"
                except:
                    # Restaurar backup si la descarga falló
                    if os.path.exists(backup_path):
                        shutil.copy2(backup_path, self.db_path)
                    return False, "Archivo descargado no es una base de datos SQLite válida"
            else:
                # Restaurar backup si la descarga falló
                if os.path.exists(backup_path):
                    shutil.copy2(backup_path, self.db_path)
                return False, msg
                
        except Exception as e:
            return False, f"Error descargando base de datos remota: {str(e)}"
    
    def subir_db_local(self) -> Tuple[bool, str]:
        """Subir base de datos local al servidor remoto"""
        if not self.gestor_ssh or not self.gestor_ssh.conectado:
            return False, "No conectado al servidor SSH"
        
        try:
            # Obtener ruta remota desde configuración
            ruta_remota = self.config.obtener('remote_paths.escuela_db', '')
            if not ruta_remota:
                return False, "Ruta remota no configurada"
            
            # Subir base de datos local
            success, msg = self.gestor_ssh.subir_archivo(self.db_path, ruta_remota)
            
            if success:
                return True, "Base de datos local subida exitosamente al servidor"
            else:
                return False, msg
                
        except Exception as e:
            return False, f"Error subiendo base de datos: {str(e)}"

# =============================================================================
# VALIDACIÓN DE DATOS (MANTENER ORIGINAL)
# =============================================================================

class ValidadorDatos:
    """Validador de datos del sistema"""
    
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
# GESTIÓN DE SESIONES (MANTENER ORIGINAL)
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

# =============================================================================
# SISTEMA PRINCIPAL CON CORRECCIÓN DE ERROR
# =============================================================================

class SistemaGestionEscolar:
    """Sistema principal con conexión SSH al servidor remoto"""
    
    def __init__(self):
        # Inicializar componentes
        self.config = ConfiguracionSistema()
        self.gestor_ssh = GestorSSH(self.config)
        self.db = GestorBaseDatos(self.config, self.gestor_ssh)
        self.validador = ValidadorDatos()
        self.sesion = GestorSesion()
        
        # Cache para datos frecuentes
        self._cache_estadisticas = None
        self._cache_timestamp = None
        self._cache_ttl = self.config.obtener('app.cache_ttl', 300)
        
        # Estado del sistema
        self.modo_operacion = self.config.obtener('app.modo', 'nube')
        self.ultima_sincronizacion = None
        self.estado_aplicacion = 'inicializado'
        
        # Inicializar sistema
        self._inicializar_sistema()
    
    def _inicializar_sistema(self):
        """Inicializar el sistema"""
        # Crear directorios necesarios
        for dir_path in ['uploads/estudiantes', 'uploads/documentos', 'logs']:
            os.makedirs(dir_path, exist_ok=True)
        
        print("✅ Sistema inicializado correctamente")
    
    # =========================================================================
    # MÉTODOS PARA ESTUDIANTES (MANTENER ORIGINAL)
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
    # MÉTODOS DE SINCRONIZACIÓN SSH
    # =========================================================================
    
    def conectar_ssh(self) -> Tuple[bool, str]:
        """Conectar al servidor SSH"""
        return self.gestor_ssh.conectar()
    
    def descargar_db_remota(self) -> Tuple[bool, str]:
        """Descargar base de datos remota"""
        success, msg = self.db.descargar_db_remota()
        if success:
            self.ultima_sincronizacion = datetime.now()
            self.limpiar_cache()  # Limpiar cache después de sincronización
        return success, msg
    
    def subir_db_local(self) -> Tuple[bool, str]:
        """Subir base de datos local al servidor"""
        success, msg = self.db.subir_db_local()
        if success:
            self.ultima_sincronizacion = datetime.now()
        return success, msg
    
    def obtener_estado_ssh(self) -> Dict[str, Any]:
        """Obtener estado de la conexión SSH"""
        return self.gestor_ssh.obtener_estado()
    
    def limpiar_cache(self):
        """Limpiar cache del sistema"""
        self._cache_estadisticas = None
        self._cache_timestamp = None
    
    def obtener_estado_sistema(self) -> Dict[str, Any]:
        """Obtener estado completo del sistema"""
        estado_ssh = self.gestor_ssh.obtener_estado()
        
        return {
            'aplicacion': {
                'estado': self.estado_aplicacion,
                'modo': self.modo_operacion,
                'version': self.config.obtener('app.version'),
                'ssh_conectado': estado_ssh['conectado'],
                'ultima_sincronizacion': self.ultima_sincronizacion
            },
            'sesion': self.sesion.obtener_info_sesion(),
            'estadisticas': self.obtener_estadisticas_rapidas()
        }

# =============================================================================
# INTERFAZ DE USUARIO MODIFICADA
# =============================================================================

class InterfazUsuario:
    """Clase para manejar la interfaz de usuario"""
    
    def __init__(self, sistema: SistemaGestionEscolar):
        self.sistema = sistema
        self.config = sistema.config
    
    def mostrar_barra_lateral(self) -> str:
        """Mostrar barra lateral con información de conexión SSH"""
        with st.sidebar:
            # Logo y título
            st.markdown(f"""
            <div style="text-align: center;">
                <h1 style="color: #1E88E5;">{self.config.obtener('app.title')}</h1>
                <p style="color: #666; font-size: 0.9em;">Versión {self.config.obtener('app.version')}</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Estado del sistema con información SSH
            st.subheader("🌐 Estado de Conexión")
            
            estado_ssh = self.sistema.obtener_estado_ssh()
            
            if estado_ssh['conectado']:
                st.success(f"✅ Conectado a {estado_ssh['host']}")
                if estado_ssh['ultima_conexion']:
                    st.caption(f"Última conexión: {estado_ssh['ultima_conexion'].strftime('%H:%M:%S')}")
            else:
                st.error("❌ No conectado al servidor")
                if estado_ssh['error_conexion']:
                    st.caption(f"Error: {estado_ssh['error_conexion']}")
            
            # Información de servidor
            with st.expander("📡 Información del servidor"):
                if estado_ssh['host']:
                    st.write(f"**Host:** {estado_ssh['host']}:{estado_ssh['port']}")
                    st.write(f"**Usuario:** {estado_ssh['username']}")
                    
                    # Botón para reconectar
                    if st.button("🔄 Reconectar", use_container_width=True):
                        success, msg = self.sistema.conectar_ssh()
                        if success:
                            st.success(f"✅ {msg}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            
            st.markdown("---")
            
            # Navegación principal
            st.subheader("🧭 Navegación")
            
            opciones = [
                "🏠 Panel de Control",
                "👨‍🎓 Gestión de Estudiantes",
                "📝 Gestión de Inscripciones",
                "🎓 Gestión de Egresados",
                "💼 Seguimiento de Contratados",
                "⚙️ Configuración del Sistema",
                "🔄 Sincronización"
            ]
            
            opcion_seleccionada = st.radio(
                "Seleccionar módulo:",
                opciones,
                label_visibility="collapsed"
            )
            
            st.markdown("---")
            
            # Acciones de sincronización
            st.subheader("🔄 Acciones de Sincronización")
            
            estado_ssh = self.sistema.obtener_estado_ssh()
            
            if estado_ssh['conectado']:
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📥 Descargar", use_container_width=True, help="Descargar datos del servidor"):
                        with st.spinner("Descargando..."):
                            success, msg = self.sistema.descargar_db_remota()
                            if success:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                
                with col2:
                    if st.button("📤 Subir", use_container_width=True, help="Subir datos al servidor"):
                        with st.spinner("Subiendo..."):
                            success, msg = self.sistema.subir_db_local()
                            if success:
                                st.success(f"✅ {msg}")
                            else:
                                st.error(f"❌ {msg}")
            else:
                st.warning("Conecte al servidor para sincronizar")
            
            st.markdown("---")
            
            # Información de versión
            estado = self.sistema.obtener_estado_sistema()
            st.caption(f"v{estado['aplicacion']['version']} | SSH: {'✅' if estado_ssh['conectado'] else '❌'}")
            
            return opcion_seleccionada
    
    def mostrar_panel_control(self):
        """Mostrar panel de control principal"""
        st.title("📊 Panel de Control")
        
        # Información del sistema
        estado = self.sistema.obtener_estado_sistema()
        estado_ssh = self.sistema.obtener_estado_ssh()
        
        with st.expander("ℹ️ Información del sistema", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Estado:**", estado['aplicacion']['estado'].capitalize())
                st.write("**Modo:**", estado['aplicacion']['modo'].capitalize())
                st.write("**Versión:**", estado['aplicacion']['version'])
            
            with col2:
                if estado_ssh['conectado']:
                    st.success("🔗 SSH Conectado")
                    st.write(f"**Host:** {estado_ssh['host']}")
                else:
                    st.error("❌ SSH No conectado")
                
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
    
    def mostrar_panel_sincronizacion(self):
        """Mostrar panel de sincronización"""
        st.title("🔄 Sincronización con Servidor Remoto")
        
        estado_ssh = self.sistema.obtener_estado_ssh()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📡 Estado de Conexión")
            
            if estado_ssh['conectado']:
                st.success(f"✅ Conectado a {estado_ssh['host']}")
                
                # Probar conexión
                if st.button("🧪 Probar conexión"):
                    success, msg = self.sistema.gestor_ssh.ejecutar_comando("pwd")
                    if success:
                        st.success(f"✅ Conexión activa: {msg}")
                    else:
                        st.error(f"❌ {msg}")
                
                # Verificar archivos remotos
                ruta_remota = self.config.obtener('ssh.remote_dir', '/home/POLANCO6/ESCUELANUEVA5')
                if st.button("📁 Ver archivos en servidor"):
                    success, archivos = self.sistema.gestor_ssh.listar_directorio(ruta_remota)
                    if success:
                        st.write("**Archivos en servidor:**")
                        for archivo in archivos[:20]:  # Mostrar primeros 20
                            st.write(f"• {archivo}")
                    else:
                        st.error("No se pudo listar archivos")
            else:
                st.error("❌ No conectado")
                
                # Conectar manualmente
                if st.button("🔗 Conectar ahora", type="primary"):
                    success, msg = self.sistema.conectar_ssh()
                    if success:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")
        
        with col2:
            st.subheader("⚙️ Configuración SSH")
            
            st.write(f"**Host:** {estado_ssh['host']}")
            st.write(f"**Puerto:** {estado_ssh['port']}")
            st.write(f"**Usuario:** {estado_ssh['username']}")
            
            # Mostrar rutas remotas configuradas
            ruta_escuela_db = self.config.obtener('remote_paths.escuela_db', 'No configurada')
            st.write(f"**Base de datos remota:** {ruta_escuela_db}")
            
            if estado_ssh['ultima_conexion']:
                st.write(f"**Última conexión:** {estado_ssh['ultima_conexion'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            if estado_ssh['error_conexion']:
                st.warning(f"**Último error:** {estado_ssh['error_conexion']}")
        
        st.markdown("---")
        
        # Acciones de sincronización
        st.subheader("📊 Sincronización de Datos")
        
        if estado_ssh['conectado']:
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📥 Descargar desde servidor", type="primary", use_container_width=True):
                    with st.spinner("Descargando datos del servidor..."):
                        success, msg = self.sistema.descargar_db_remota()
                        if success:
                            st.success(f"✅ {msg}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            
            with col2:
                if st.button("📤 Subir al servidor", use_container_width=True):
                    with st.spinner("Subiendo datos al servidor..."):
                        success, msg = self.sistema.subir_db_local()
                        if success:
                            st.success(f"✅ {msg}")
                        else:
                            st.error(f"❌ {msg}")
            
            # Información adicional
            st.info("""
            **Nota:** La sincronización reemplazará completamente la base de datos local o remota.
            Asegúrese de tener un backup antes de realizar operaciones de sincronización.
            """)
        else:
            st.warning("⚠️ Conecte al servidor para habilitar sincronización")
    
    # Mantener los métodos restantes de la interfaz original...
    # mostrar_gestion_estudiantes, mostrar_gestion_inscripciones, etc.
    # (Estos métodos permanecen igual que en tu código original)
    
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
        
        # Obtener estudiantes
        estudiantes = self.sistema.obtener_estudiantes(
            filtro_estado if filtro_estado != 'Todos' else None,
            filtro_nivel if filtro_nivel != 'Todos' else None,
            busqueda if busqueda else None,
            100  # Límite de 100 para vista inicial
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
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        nuevo_estado = st.selectbox(
                            "Cambiar estado:",
                            self.config.obtener('estados.estudiante', []),
                            key=f"estado_{estudiante_id}"
                        )
                        if st.button("🔄 Actualizar estado", use_container_width=True):
                            success, msg = self.sistema.cambiar_estado_estudiante(estudiante_id, nuevo_estado)
                            if success:
                                st.success(f"✅ {msg}")
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
                    
                    with col2:
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
    
    def mostrar_gestion_inscripciones(self):
        """Mostrar interfaz de gestión de inscripciones"""
        st.title("📝 Gestión de Inscripciones")
        
        # Obtener ciclo escolar actual
        ciclo_actual = "2024-2025"  # Esto se puede mejorar
        st.info(f"🏫 Ciclo escolar sugerido: **{ciclo_actual}**")
        
        tab1, tab2 = st.tabs(["📋 Inscripciones", "➕ Nueva Inscripción"])
        
        with tab1:
            inscripciones = self.sistema.obtener_inscripciones()
            if inscripciones:
                datos = []
                for ins in inscripciones:
                    datos.append({
                        'ID': ins['id'],
                        'Matrícula': ins['matricula'],
                        'Estudiante': f"{ins['nombre']} {ins['apellido_paterno']}",
                        'Ciclo': ins['ciclo_escolar'],
                        'Semestre': ins['semestre'],
                        'Estatus': ins['estatus']
                    })
                
                df = pd.DataFrame(datos)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("📭 No hay inscripciones registradas")
        
        with tab2:
            st.subheader("Nueva Inscripción")
            
            # Obtener estudiantes activos
            estudiantes = self.sistema.obtener_estudiantes('Activo', None, 50)
            
            if estudiantes:
                estudiante_opciones = {
                    f"{e['id']} - {e['matricula']} - {e['nombre']} {e['apellido_paterno']}": e['id']
                    for e in estudiantes
                }
                
                estudiante_seleccionado = st.selectbox(
                    "Seleccionar estudiante:",
                    list(estudiante_opciones.keys())
                )
                
                if estudiante_seleccionado:
                    estudiante_id = estudiante_opciones[estudiante_seleccionado]
                    ciclo_escolar = st.text_input("Ciclo escolar:", value=ciclo_actual)
                    semestre = st.number_input("Semestre:", min_value=1, max_value=20, value=1)
                    
                    if st.button("📝 Inscribir Estudiante", type="primary"):
                        success, msg, _ = self.sistema.inscribir_estudiante(
                            estudiante_id, ciclo_escolar, semestre
                        )
                        if success:
                            st.success(f"✅ {msg}")
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
            else:
                st.warning("No hay estudiantes activos para inscribir")
    
    def mostrar_gestion_egresados(self):
        """Mostrar interfaz de gestión de egresados"""
        st.title("🎓 Gestión de Egresados")
        
        tab1, tab2 = st.tabs(["📋 Lista de Egresados", "➕ Registrar Egresado"])
        
        with tab1:
            egresados = self.sistema.obtener_egresados()
            if egresados:
                datos = []
                for eg in egresados:
                    datos.append({
                        'ID': eg['id'],
                        'Matrícula': eg['matricula'],
                        'Egresado': f"{eg['nombre']} {eg['apellido_paterno']}",
                        'Carrera': eg['carrera'],
                        'Título': eg['titulo_obtenido'],
                        'Fecha Egreso': eg['fecha_egreso'][:10] if eg['fecha_egreso'] else ''
                    })
                
                df = pd.DataFrame(datos)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("📭 No hay egresados registrados")
        
        with tab2:
            st.subheader("Registrar Egresado")
            
            # Listar estudiantes que podrían ser egresados
            estudiantes = self.sistema.obtener_estudiantes('Activo', None, 50)
            
            if estudiantes:
                estudiante_opciones = {
                    f"{e['id']} - {e['matricula']} - {e['nombre']} {e['apellido_paterno']}": e['id']
                    for e in estudiantes
                }
                
                estudiante_seleccionado = st.selectbox(
                    "Seleccionar estudiante:",
                    list(estudiante_opciones.keys())
                )
                
                if estudiante_seleccionado:
                    estudiante_id = estudiante_opciones[estudiante_seleccionado]
                    fecha_egreso = st.date_input("Fecha de Egreso", value=datetime.now())
                    titulo_obtenido = st.text_input("Título Obtenido", max_chars=200)
                    promedio_final = st.number_input("Promedio Final", min_value=0.0, max_value=10.0, value=8.0, step=0.1)
                    
                    if st.button("🎓 Registrar Egresado", type="primary"):
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
            else:
                st.warning("No hay estudiantes disponibles para registrar como egresados")
    
    def mostrar_gestion_contrataciones(self):
        """Mostrar interfaz de seguimiento de contratados"""
        st.title("💼 Seguimiento de Contratados")
        
        contratados = self.sistema.obtener_contratados()
        
        if contratados:
            datos = []
            for cont in contratados:
                datos.append({
                    'ID': cont['id'],
                    'Matrícula': cont['matricula'],
                    'Contratado': f"{cont['nombre']} {cont['apellido_paterno']}",
                    'Carrera': cont['carrera'],
                    'Empresa': cont['empresa'],
                    'Puesto': cont['puesto'],
                    'Salario': f"${cont['salario_actual'] or cont['salario_inicial']:,.2f}" 
                               if cont['salario_actual'] or cont['salario_inicial'] else 'No especificado'
                })
            
            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Exportar a Excel
            if st.button("📊 Exportar a Excel"):
                output, nombre = self.sistema.generar_informe_excel('contratados')
                if output:
                    st.download_button(
                        label="⬇️ Descargar Excel",
                        data=output,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        else:
            st.info("📭 No hay contrataciones registradas")
    
    def mostrar_configuracion_sistema(self):
        """Mostrar configuración del sistema"""
        st.title("⚙️ Configuración del Sistema")
        
        tab1, tab2 = st.tabs(["📊 Estado del Sistema", "💾 Backup"])
        
        with tab1:
            self._mostrar_estado_sistema()
        
        with tab2:
            self._mostrar_backup()
    
    def _mostrar_estado_sistema(self):
        """Mostrar estado actual del sistema"""
        st.subheader("📊 Estado del Sistema")
        
        estado = self.sistema.obtener_estado_sistema()
        estado_ssh = self.sistema.obtener_estado_ssh()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Estado general:**", estado['aplicacion']['estado'].capitalize())
            st.write("**Modo de operación:**", estado['aplicacion']['modo'].capitalize())
            st.write("**Versión:**", estado['aplicacion']['version'])
            
            if estado_ssh['conectado']:
                st.success(f"✅ SSH Conectado a {estado_ssh['host']}")
            else:
                st.error("❌ SSH Desconectado")
        
        with col2:
            st.write("**Sesión iniciada:**", estado['sesion']['iniciada'])
            st.write("**Duración de sesión:**", estado['sesion']['duracion'])
            st.write("**Estudiantes esta sesión:**", estado['estadisticas']['estudiantes_sesion'])
            
            if estado['aplicacion']['ultima_sincronizacion']:
                st.write("**Última sincronización:**", estado['aplicacion']['ultima_sincronizacion'].strftime('%Y-%m-%d %H:%M'))
    
    def _mostrar_backup(self):
        """Mostrar opciones de backup"""
        st.subheader("💾 Sistema de Backup")
        
        # Información sobre backups
        st.info("""
        **Nota sobre backups:**
        - Los backups se guardan localmente en el directorio `backups/`
        - Se recomienda descargar manualmente los backups importantes
        - En modo nube, los backups son temporales para la sesión actual
        """)
        
        # Crear backup manual
        if st.button("💾 Crear Backup Manual", type="primary"):
            st.info("Funcionalidad de backup en desarrollo")

# =============================================================================
# FUNCIÓN PRINCIPAL MODIFICADA
# =============================================================================

def main():
    """Función principal de la aplicación"""
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
            except Exception as e:
                st.error(f"❌ Error crítico al inicializar el sistema: {e}")
                st.exception(e)
                st.stop()
    
    sistema = st.session_state.sistema
    ui = st.session_state.ui
    
    # Mostrar barra lateral y obtener opción
    try:
        opcion = ui.mostrar_barra_lateral()
    except Exception as e:
        st.error(f"❌ Error en barra lateral: {e}")
        opcion = "🏠 Panel de Control"
    
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
            ui.mostrar_gestion_contrataciones()
        
        elif opcion == "⚙️ Configuración del Sistema":
            ui.mostrar_configuracion_sistema()
        
        elif opcion == "🔄 Sincronización":
            ui.mostrar_panel_sincronizacion()
    
    except Exception as e:
        st.error(f"❌ Error en la aplicación: {e}")
        st.exception(e)
    
    # Pie de página
    st.markdown("---")
    
    try:
        estado_ssh = sistema.obtener_estado_ssh()
        estado_conexion = "✅ Conectado" if estado_ssh['conectado'] else "❌ Desconectado"
        host_info = f" a {estado_ssh['host']}" if estado_ssh['host'] else ""
        
        st.caption(f"© 2024 Sistema de Gestión Escolar v{sistema.config.obtener('app.version')} | SSH: {estado_conexion}{host_info}")
    except:
        st.caption(f"© 2024 Sistema de Gestión Escolar")

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    main()
