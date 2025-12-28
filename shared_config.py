"""
shared_config.py - Configuración compartida para todos los sistemas
Módulo centralizado para evitar duplicación y conflictos
Versión corregida para Streamlit Cloud
"""

import os
import sys
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# =============================================================================
# IMPORTACIONES CONDICIONALES - CORREGIDO
# =============================================================================

# Mover importaciones al nivel superior para evitar problemas de scope
try:
    import tomllib  # Python 3.11+
    HAS_TOMLLIB = True
except ImportError:
    try:
        import tomli as tomllib  # Python < 3.11
        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        tomllib = None

# Importar paramiko y socket al nivel superior para evitar problemas de scope
try:
    import paramiko
    import socket
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False
    paramiko = None
    socket = None

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

# =============================================================================
# CONFIGURACIÓN DE LOGGING COMPARTIDO
# =============================================================================

class SistemaLogging:
    """Sistema de logging centralizado para todos los sistemas"""
    
    _instancias = {}
    
    @classmethod
    def obtener_logger(cls, nombre_sistema: str, archivo_log: str = None):
        """Obtener o crear logger para un sistema específico"""
        if nombre_sistema not in cls._instancias:
            cls._instancias[nombre_sistema] = cls._crear_logger(nombre_sistema, archivo_log)
        return cls._instancias[nombre_sistema]
    
    @staticmethod
    def _crear_logger(nombre_sistema: str, archivo_log: str = None):
        """Crear logger específico para un sistema"""
        logger = logging.getLogger(f"escuela.{nombre_sistema}")
        
        # Evitar duplicación de handlers
        if logger.handlers:
            return logger
        
        logger.setLevel(logging.DEBUG)
        
        # Formato detallado
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Handler para archivo (solo si se especifica y es posible)
        if archivo_log:
            try:
                # En Streamlit Cloud, intentar crear en directorio temporal
                import tempfile
                temp_dir = tempfile.gettempdir()
                log_path = os.path.join(temp_dir, archivo_log)
                
                file_handler = logging.FileHandler(log_path, encoding='utf-8')
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                print(f"⚠️ No se pudo crear archivo de log {archivo_log}: {e}")
                # Continuar solo con consola
        
        logger.addHandler(console_handler)
        return logger

# =============================================================================
# CARGADOR DE CONFIGURACIÓN CENTRALIZADO
# =============================================================================

class CargadorConfiguracion:
    """Carga y gestiona configuración desde secrets.toml"""
    
    _config_cache = None
    
    @classmethod
    def cargar_configuracion(cls):
        """Cargar configuración una sola vez y cachearla"""
        if cls._config_cache is None:
            try:
                cls._config_cache = cls._cargar_desde_archivo()
            except Exception as e:
                print(f"⚠️ Error cargando configuración: {e}")
                cls._config_cache = cls._configuracion_por_defecto()
        return cls._config_cache
    
    @staticmethod
    def _cargar_desde_archivo() -> Dict[str, Any]:
        """Cargar configuración desde secrets.toml"""
        if not HAS_TOMLLIB or tomllib is None:
            raise ImportError("tomllib/tomli no está disponible. Instalar con: pip install tomli")
        
        # Buscar el archivo secrets.toml en posibles ubicaciones
        posibles_rutas = [
            ".streamlit/secrets.toml",
            "secrets.toml",
            "./.streamlit/secrets.toml",
            "../.streamlit/secrets.toml",
            "/mount/src/escuelanueva5/.streamlit/secrets.toml",
            "/mount/src/escuelanueva5/secrets.toml",
            "config/secrets.toml"
        ]
        
        ruta_encontrada = None
        for ruta in posibles_rutas:
            if os.path.exists(ruta):
                ruta_encontrada = ruta
                print(f"✅ Encontrado secrets.toml en: {ruta}")
                break
        
        if not ruta_encontrada:
            raise FileNotFoundError("No se encontró secrets.toml. Asegúrate de configurarlo en Streamlit Cloud Secrets.")
        
        # Leer el archivo
        with open(ruta_encontrada, 'rb') as f:
            config = tomllib.load(f)
        
        print(f"✅ Configuración cargada desde {ruta_encontrada}")
        return config
    
    @staticmethod
    def _configuracion_por_defecto() -> Dict[str, Any]:
        """Configuración por defecto cuando no hay secrets.toml"""
        print("⚠️ Usando configuración por defecto (modo local sin SSH)")
        
        return {
            'ssh': {
                'enabled': False,
                'host': '',
                'port': 22,
                'username': '',
                'password': '',
                'timeout': 30
            },
            'remote_paths': {},
            'timeouts': {
                'ssh_connect': 30,
                'ssh_command': 60,
                'sftp_transfer': 300,
                'db_download': 180,
                'db_upload': 180
            },
            'backup': {
                'enabled': False,
                'max_backups': 10,
                'min_disk_space_mb': 100,
                'auto_backup_before_migration': True
            },
            'system': {
                'supervisor_mode': False,
                'debug_mode': True
            },
            'smtp': {
                'server': '',
                'port': 587,
                'email_user': '',
                'email_password': '',
                'notification_email': ''
            },
            'escuela': {
                'estado_file': 'estado_escuela.json',
                'log_file': 'escuela_detallado.log',
                'migrations_log': 'escuela_migrations.json',
                'backup_dir': 'backups_escuela',
                'sync_on_start': False,
                'auto_connect': False,
                'page_size': 50,
                'cache_ttl': 300
            }
        }
    
    @classmethod
    def obtener_config_sistema(cls, nombre_sistema: str) -> Dict[str, Any]:
        """Obtener configuración específica para un sistema"""
        config = cls.cargar_configuracion()
        
        # Configuración base común (siempre disponible)
        config_base = {
            'ssh': config.get('ssh', {}),
            'remote_paths': config.get('remote_paths', {}),
            'timeouts': config.get('timeouts', {}),
            'backup': config.get('backup', {}),
            'system': config.get('system', {}),
            'smtp': config.get('smtp', {})
        }
        
        # Configuración específica del sistema
        if nombre_sistema in config:
            sistema_config = config[nombre_sistema]
            # Si es un diccionario, fusionarlo
            if isinstance(sistema_config, dict):
                config_base.update(sistema_config)
            else:
                print(f"⚠️ Configuración para {nombre_sistema} no es un diccionario, ignorando")
        else:
            print(f"⚠️ No se encontró configuración específica para {nombre_sistema}")
        
        # Validar y completar configuraciones faltantes
        config_base = ValidacionConfiguracion.validar_y_completar_config(config_base, nombre_sistema)
        
        return config_base

# =============================================================================
# VALIDACIÓN DE CONFIGURACIÓN
# =============================================================================

class ValidacionConfiguracion:
    """Validar y normalizar configuración"""
    
    @staticmethod
    def validar_y_completar_config(config: dict, sistema: str) -> dict:
        """Validar y completar configuraciones faltantes"""
        config_validada = config.copy()
        
        # Valores por defecto esenciales para cualquier sistema
        defaults = {
            'estado_file': f'estado_{sistema}.json',
            'log_file': f'{sistema}_detallado.log',
            'page_size': 50,
            'cache_ttl': 300,
            'sync_on_start': False,
            'auto_connect': False,
            'backup_dir': f'backups_{sistema}'
        }
        
        # Aplicar defaults si no existen
        for key, value in defaults.items():
            if key not in config_validada:
                config_validada[key] = value
        
        # Asegurar estructura de backup
        if 'backup' not in config_validada or not isinstance(config_validada['backup'], dict):
            config_validada['backup'] = {}
        
        backup_defaults = {
            'enabled': True,
            'max_backups': 10,
            'min_disk_space_mb': 100,
            'auto_backup_before_migration': True
        }
        
        for key, value in backup_defaults.items():
            if key not in config_validada['backup']:
                config_validada['backup'][key] = value
        
        # Asegurar que ssh tiene estructura correcta
        if 'ssh' not in config_validada:
            config_validada['ssh'] = {'enabled': False}
        
        ssh_defaults = {
            'enabled': False,
            'host': '',
            'port': 22,
            'username': '',
            'password': '',
            'timeout': 30
        }
        
        for key, value in ssh_defaults.items():
            if key not in config_validada['ssh']:
                config_validada['ssh'][key] = value
        
        # Asegurar estructura de timeouts
        if 'timeouts' not in config_validada or not isinstance(config_validada['timeouts'], dict):
            config_validada['timeouts'] = {}
        
        timeouts_defaults = {
            'ssh_connect': 30,
            'ssh_command': 60,
            'sftp_transfer': 300,
            'db_download': 180,
            'db_upload': 180
        }
        
        for key, value in timeouts_defaults.items():
            if key not in config_validada['timeouts']:
                config_validada['timeouts'][key] = value
        
        return config_validada

# =============================================================================
# CLASES BASE PARA ESTADO PERSISTENTE
# =============================================================================

class EstadoPersistenteBase:
    """Clase base para estado persistente de cualquier sistema"""
    
    def __init__(self, archivo_estado: str, nombre_sistema: str):
        self.archivo_estado = archivo_estado
        self.nombre_sistema = nombre_sistema
        self.logger = SistemaLogging.obtener_logger(nombre_sistema)
        self.estado = self._cargar_estado()
    
    def _cargar_estado(self) -> Dict[str, Any]:
        """Cargar estado desde archivo JSON"""
        try:
            # En Streamlit Cloud, usar directorio temporal
            import tempfile
            temp_dir = tempfile.gettempdir()
            estado_path = os.path.join(temp_dir, self.archivo_estado)
            
            if os.path.exists(estado_path):
                with open(estado_path, 'r', encoding='utf-8') as f:
                    estado = json.load(f)
                    # Asegurar estructura básica
                    return self._migrar_estructura_estado(estado)
            else:
                # Verificar también en directorio actual por compatibilidad
                if os.path.exists(self.archivo_estado):
                    with open(self.archivo_estado, 'r', encoding='utf-8') as f:
                        estado = json.load(f)
                        return self._migrar_estructura_estado(estado)
                        
        except Exception as e:
            self.logger.warning(f"⚠️ Error cargando estado {self.archivo_estado}: {e}")
        
        return self._estado_por_defecto()
    
    def _migrar_estructura_estado(self, estado: Dict[str, Any]) -> Dict[str, Any]:
        """Migrar estructura antigua si es necesario"""
        # Versión de estructura
        if 'version_estructura' not in estado:
            estado['version_estructura'] = '1.0'
        
        # Migrar de v1.0 a v2.0
        if estado['version_estructura'] == '1.0':
            if 'migraciones_realizadas' in estado:
                estado['estadisticas_migracion'] = {
                    'exitosas': estado.get('migraciones_realizadas', 0),
                    'fallidas': estado.get('migraciones_fallidas', 0),
                    'total_tiempo': estado.get('tiempo_total_migracion', 0)
                }
                # No eliminar para compatibilidad
            estado['version_estructura'] = '2.0'
        
        # Asegurar estructura básica
        defaults = self._estado_por_defecto()
        for key, value in defaults.items():
            if key not in estado:
                estado[key] = value
        
        return estado
    
    def _estado_por_defecto(self) -> Dict[str, Any]:
        """Estado por defecto para cualquier sistema"""
        return {
            'sistema': self.nombre_sistema,
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': 'remoto',
            'ssh_conectado': False,
            'ssh_error': None,
            'ultima_verificacion': None,
            'estadisticas_migracion': {
                'exitosas': 0,
                'fallidas': 0,
                'total_tiempo': 0
            },
            'backups_realizados': 0,
            'migraciones_realizadas': 0,  # Mantener por compatibilidad
            'migraciones_fallidas': 0,    # Mantener por compatibilidad
            'tiempo_total_migracion': 0,  # Mantener por compatibilidad
            'version_estructura': '2.0'
        }
    
    def guardar_estado(self):
        """Guardar estado a archivo JSON"""
        try:
            # En Streamlit Cloud, usar directorio temporal
            import tempfile
            temp_dir = tempfile.gettempdir()
            estado_path = os.path.join(temp_dir, self.archivo_estado)
            
            with open(estado_path, 'w', encoding='utf-8') as f:
                json.dump(self.estado, f, indent=2, default=str)
            self.logger.debug(f"Estado guardado en {estado_path}")
        except Exception as e:
            self.logger.error(f"❌ Error guardando estado: {e}")
            # Intentar en directorio actual como fallback
            try:
                with open(self.archivo_estado, 'w', encoding='utf-8') as f:
                    json.dump(self.estado, f, indent=2, default=str)
            except Exception as e2:
                self.logger.error(f"❌ Error crítico guardando estado: {e2}")
    
    def marcar_db_inicializada(self):
        """Marcar la base de datos como inicializada"""
        self.estado['db_inicializada'] = True
        self.estado['fecha_inicializacion'] = self._timestamp_actual()
        self.guardar_estado()
        self.logger.info(f"✅ Base de datos marcada como inicializada para {self.nombre_sistema}")
    
    def marcar_sincronizacion(self):
        """Marcar última sincronización"""
        self.estado['ultima_sincronizacion'] = self._timestamp_actual()
        self.guardar_estado()
    
    def set_ssh_conectado(self, conectado: bool, error: str = None):
        """Establecer estado de conexión SSH"""
        self.estado['ssh_conectado'] = conectado
        self.estado['ssh_error'] = error
        self.estado['ultima_verificacion'] = self._timestamp_actual()
        self.guardar_estado()
    
    def registrar_migracion(self, exitosa: bool = True, tiempo_ejecucion: float = 0):
        """Registrar una migración"""
        self.estado['migraciones_realizadas'] = self.estado.get('migraciones_realizadas', 0) + 1
        
        if exitosa:
            self.estado['estadisticas_migracion']['exitosas'] += 1
        else:
            self.estado['estadisticas_migracion']['fallidas'] += 1
        
        self.estado['estadisticas_migracion']['total_tiempo'] += tiempo_ejecucion
        self.estado['ultima_migracion'] = self._timestamp_actual()
        self.guardar_estado()
    
    def registrar_backup(self):
        """Registrar que se realizó un backup"""
        self.estado['backups_realizados'] = self.estado.get('backups_realizados', 0) + 1
        self.guardar_estado()
    
    def _timestamp_actual(self):
        """Obtener timestamp actual en formato ISO"""
        return datetime.now().isoformat()
    
    def esta_inicializada(self) -> bool:
        """Verificar si la BD está inicializada"""
        return self.estado.get('db_inicializada', False)
    
    def obtener_fecha_inicializacion(self):
        """Obtener fecha de inicialización"""
        fecha_str = self.estado.get('fecha_inicializacion')
        if fecha_str:
            try:
                return datetime.fromisoformat(fecha_str)
            except:
                return None
        return None
    
    def obtener_estadisticas(self) -> Dict[str, Any]:
        """Obtener estadísticas del sistema"""
        return self.estado.get('estadisticas_migracion', {})

# =============================================================================
# GESTOR DE CONEXIÓN SSH COMPARTIDO - CORREGIDO
# =============================================================================

class GestorSSHCompartido:
    """Gestor de conexión SSH compartido para todos los sistemas"""
    
    _instancia = None
    _ssh_client = None
    _sftp_client = None
    
    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializar()
        return cls._instancia
    
    def _inicializar(self):
        """Inicializar gestor SSH"""
        try:
            # Obtener configuración completa
            self.config = CargadorConfiguracion.cargar_configuracion()
            self.logger = SistemaLogging.obtener_logger('ssh_shared')
            self.ssh_config = self.config.get('ssh', {})
            
            if not HAS_PARAMIKO:
                self.logger.warning("⚠️ paramiko no está instalado. Instalar con: pip install paramiko")
                self.ssh_config['enabled'] = False
            
            if not self.ssh_config.get('enabled', True):
                self.logger.info("SSH deshabilitado en configuración")
                
        except Exception as e:
            self.logger = SistemaLogging.obtener_logger('ssh_shared')
            self.logger.error(f"Error inicializando SSH: {e}")
            self.ssh_config = {'enabled': False}
    
    def conectar(self) -> bool:
        """Establecer conexión SSH con el servidor remoto"""
        # Verificar que paramiko esté disponible
        if not HAS_PARAMIKO or paramiko is None or socket is None:
            self.logger.error("❌ paramiko o socket no están disponibles")
            return False
        
        try:
            if not self.ssh_config.get('host'):
                self.logger.error("No hay configuración SSH disponible (host no configurado)")
                return False
            
            if not self.ssh_config.get('enabled', True):
                self.logger.warning("SSH deshabilitado en configuración")
                return False
            
            if self._ssh_client and self._verificar_conexion_activa():
                self.logger.debug("Conexión SSH ya activa, reutilizando")
                return True
            
            self.logger.info(f"🔗 Conectando SSH a {self.ssh_config['host']}:{self.ssh_config.get('port', 22)}...")
            
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            timeout = self.ssh_config.get('timeout', 30)
            
            self._ssh_client.connect(
                hostname=self.ssh_config['host'],
                port=self.ssh_config.get('port', 22),
                username=self.ssh_config['username'],
                password=self.ssh_config['password'],
                timeout=timeout,
                banner_timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            self._sftp_client = self._ssh_client.open_sftp()
            sftp_timeout = self.ssh_config.get('timeout', 300)
            self._sftp_client.get_channel().settimeout(sftp_timeout)
            
            self.logger.info(f"✅ Conexión SSH establecida a {self.ssh_config['host']}")
            return True
            
        except socket.timeout:
            self.logger.error(f"❌ Timeout conectando a {self.ssh_config.get('host', 'desconocido')}")
            return False
        except paramiko.AuthenticationException:
            self.logger.error("❌ Error de autenticación SSH - Credenciales incorrectas")
            return False
        except paramiko.SSHException as e:
            self.logger.error(f"❌ Error SSH: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Error de conexión SSH: {str(e)}")
            return False
    
    def _verificar_conexion_activa(self) -> bool:
        """Verificar si la conexión SSH está activa"""
        try:
            if self._ssh_client and self._sftp_client:
                # Intentar un comando simple
                transport = self._ssh_client.get_transport()
                if transport and transport.is_active():
                    return True
        except:
            pass
        return False
    
    def desconectar(self):
        """Cerrar conexión SSH"""
        try:
            if self._sftp_client:
                self._sftp_client.close()
            if self._ssh_client:
                self._ssh_client.close()
            self.logger.debug("🔌 Conexión SSH cerrada")
        except Exception as e:
            self.logger.warning(f"⚠️ Error cerrando conexión SSH: {e}")
        finally:
            self._ssh_client = None
            self._sftp_client = None
    
    def obtener_sftp(self):
        """Obtener cliente SFTP (conectar si es necesario)"""
        if not self._verificar_conexion_activa():
            if not self.conectar():
                return None
        return self._sftp_client
    
    def obtener_ssh(self):
        """Obtener cliente SSH (conectar si es necesario)"""
        if not self._verificar_conexion_activa():
            if not self.conectar():
                return None
        return self._ssh_client
    
    def ejecutar_comando_remoto(self, comando: str, timeout: int = 30) -> Tuple[Optional[str], Optional[str]]:
        """Ejecutar comando en servidor remoto"""
        try:
            ssh = self.obtener_ssh()
            if not ssh:
                return None, "No hay conexión SSH"
            
            stdin, stdout, stderr = ssh.exec_command(comando, timeout=timeout)
            salida = stdout.read().decode('utf-8', errors='ignore').strip()
            error = stderr.read().decode('utf-8', errors='ignore').strip()
            
            return salida, error
            
        except Exception as e:
            return None, f"Error ejecutando comando: {str(e)}"

# =============================================================================
# UTILIDADES COMPARTIDAS
# =============================================================================

class UtilidadesCompartidas:
    """Utilidades compartidas para todos los sistemas"""
    
    @staticmethod
    def verificar_espacio_disco(ruta: str, espacio_minimo_mb: int = 100) -> Tuple[bool, float]:
        """Verificar espacio disponible en disco"""
        if not HAS_PSUTIL:
            print("⚠️ psutil no está instalado. Instalar con: pip install psutil")
            return True, 0  # Asumir que hay espacio
        
        try:
            stat = psutil.disk_usage(ruta)
            espacio_disponible_mb = stat.free / (1024 * 1024)
            
            if espacio_disponible_mb < espacio_minimo_mb:
                return False, espacio_disponible_mb
            
            return True, espacio_disponible_mb
            
        except Exception as e:
            print(f"⚠️ Error verificando espacio en disco: {e}")
            return True, 0  # Asumir que hay espacio
    
    @staticmethod
    def verificar_conectividad_red(host: str = "8.8.8.8", port: int = 53, timeout: int = 3) -> bool:
        """Verificar conectividad de red"""
        try:
            import socket
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False
    
    @staticmethod
    def crear_directorio_si_no_existe(ruta: str) -> bool:
        """Crear directorio si no existe"""
        import os
        try:
            if not os.path.exists(ruta):
                os.makedirs(ruta, exist_ok=True)
                return True
            return False
        except Exception as e:
            print(f"⚠️ Error creando directorio {ruta}: {e}")
            return False
    
    @staticmethod
    def generar_timestamp() -> str:
        """Generar timestamp para nombres de archivo"""
        return datetime.now().strftime('%Y%m%d_%H%M%S')
    
    @staticmethod
    def validar_email(email: str) -> bool:
        """Validar formato de email"""
        import re
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validar_matricula(matricula: str) -> bool:
        """Validar formato de matrícula"""
        if not matricula:
            return False
        return len(matricula) >= 3 and any(char.isdigit() for char in matricula)
    
    @staticmethod
    def validar_curp(curp: str) -> bool:
        """Validar formato básico de CURP"""
        import re
        if not curp or len(curp) != 18:
            return False
        pattern = r'^[A-Z]{4}[0-9]{6}[HM][A-Z]{5}[0-9A-Z]{2}$'
        return bool(re.match(pattern, curp))
    
    @staticmethod
    def calcular_edad(fecha_nacimiento: str) -> Optional[int]:
        """Calcular edad a partir de fecha de nacimiento"""
        try:
            nacimiento = datetime.strptime(fecha_nacimiento, '%Y-%m-%d')
            hoy = datetime.now()
            edad = hoy.year - nacimiento.year
            if (hoy.month, hoy.day) < (nacimiento.month, nacimiento.day):
                edad -= 1
            return edad
        except:
            return None
    
    @staticmethod
    def formatear_dinero(cantidad: float) -> str:
        """Formatear cantidad monetaria"""
        return f"${cantidad:,.2f}"
    
    @staticmethod
    def obtener_directorio_temporal() -> str:
        """Obtener directorio temporal para Streamlit Cloud"""
        import tempfile
        return tempfile.gettempdir()
    
    @staticmethod
    def crear_archivo_temporal(extension: str = ".tmp") -> str:
        """Crear archivo temporal con extensión específica"""
        import tempfile
        temp_dir = tempfile.gettempdir()
        timestamp = UtilidadesCompartidas.generar_timestamp()
        return os.path.join(temp_dir, f"temp_{timestamp}{extension}")

# =============================================================================
# VALIDACIÓN DE CONFIGURACIÓN ESPECÍFICA
# =============================================================================

class ValidacionConfiguracionEspecifica:
    """Validación específica por sistema"""
    
    @staticmethod
    def validar_config_escuela(config: dict) -> list:
        """Validar configuración mínima para sistema escolar"""
        errores = []
        
        # Verificar configuración SSH si está habilitado
        ssh_config = config.get('ssh', {})
        if ssh_config.get('enabled', False):
            if not ssh_config.get('host'):
                errores.append("SSH habilitado pero no hay host configurado")
            if not ssh_config.get('username'):
                errores.append("SSH habilitado pero no hay usuario configurado")
            if not ssh_config.get('password'):
                errores.append("SSH habilitado pero no hay contraseña configurada")
        
        # Verificar rutas remotas si SSH está habilitado
        if ssh_config.get('enabled', False):
            remote_paths = config.get('remote_paths', {})
            if not remote_paths.get('escuela_db'):
                errores.append("SSH habilitado pero no hay ruta para escuela_db")
        
        return errores

# =============================================================================
# INICIALIZACIÓN RÁPIDA
# =============================================================================

def inicializar_sistema_rapido(nombre_sistema: str = 'escuela') -> Tuple[bool, str]:
    """Inicialización rápida para verificar que todo funciona"""
    try:
        # 1. Verificar imports
        if not HAS_TOMLLIB:
            return False, "tomllib/tomli no está instalado"
        
        if not HAS_PARAMIKO:
            return False, "paramiko no está instalado (necesario para SSH)"
        
        # 2. Cargar configuración
        config = CargadorConfiguracion.obtener_config_sistema(nombre_sistema)
        
        # 3. Verificar configuración básica
        ssh_config = config.get('ssh', {})
        if ssh_config.get('enabled', False):
            if not ssh_config.get('host'):
                return False, "SSH habilitado pero sin host"
        
        # 4. Crear logger
        logger = SistemaLogging.obtener_logger(nombre_sistema)
        logger.info(f"Sistema {nombre_sistema} inicializado correctamente")
        
        return True, "✅ Sistema inicializado correctamente"
        
    except Exception as e:
        return False, f"❌ Error inicializando sistema: {str(e)}"

# =============================================================================
# FUNCIÓN DE PRUEBA
# =============================================================================

def probar_configuracion():
    """Función para probar la configuración"""
    print("🧪 Probando configuración compartida...")
    
    # Probar cargador de configuración
    try:
        config = CargadorConfiguracion.cargar_configuracion()
        print(f"✅ Configuración cargada: {len(config)} secciones")
    except Exception as e:
        print(f"❌ Error cargando configuración: {e}")
    
    # Probar sistema de logging
    logger = SistemaLogging.obtener_logger('test')
    logger.info("✅ Logging funcionando")
    
    # Probar utilidades
    util = UtilidadesCompartidas()
    timestamp = util.generar_timestamp()
    print(f"✅ Timestamp generado: {timestamp}")
    
    print("✅ Pruebas completadas")

# =============================================================================
# EJECUCIÓN DIRECTA
# =============================================================================

if __name__ == "__main__":
    probar_configuracion()
