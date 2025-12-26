"""
shared_config.py - Configuración compartida para todos los sistemas
Módulo centralizado para evitar duplicación y conflictos
"""

import os
import sys
import logging
from typing import Dict, Any, Optional
import warnings
warnings.filterwarnings('ignore')

# Intentar importar tomllib (Python 3.11+) o tomli (Python < 3.11)
try:
    import tomllib  # Python 3.11+
    HAS_TOMLLIB = True
except ImportError:
    try:
        import tomli as tomllib  # Python < 3.11
        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        print("❌ ERROR CRÍTICO: No se encontró tomllib o tomli. Instalar con: pip install tomli")
        sys.exit(1)

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
        logger.setLevel(logging.DEBUG)
        
        # Evitar duplicación de handlers
        if logger.handlers:
            return logger
        
        # Formato detallado
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Handler para archivo
        if archivo_log:
            file_handler = logging.FileHandler(archivo_log, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
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
            cls._config_cache = cls._cargar_desde_archivo()
        return cls._config_cache
    
    @staticmethod
    def _cargar_desde_archivo() -> Dict[str, Any]:
        """Cargar configuración desde secrets.toml"""
        if not HAS_TOMLLIB:
            raise ImportError("tomllib/tomli no está disponible")
        
        # Buscar el archivo secrets.toml en posibles ubicaciones
        posibles_rutas = [
            ".streamlit/secrets.toml",
            "secrets.toml",
            "./.streamlit/secrets.toml",
            "../.streamlit/secrets.toml",
            "/mount/src/escuelanueva/.streamlit/secrets.toml",
            "config/secrets.toml"
        ]
        
        ruta_encontrada = None
        for ruta in posibles_rutas:
            if os.path.exists(ruta):
                ruta_encontrada = ruta
                break
        
        if not ruta_encontrada:
            raise FileNotFoundError("No se encontró secrets.toml en ninguna ubicación")
        
        # Leer el archivo
        with open(ruta_encontrada, 'rb') as f:
            return tomllib.load(f)
    
    @classmethod
    def obtener_config_sistema(cls, nombre_sistema: str) -> Dict[str, Any]:
        """Obtener configuración específica para un sistema"""
        config = cls.cargar_configuracion()
        
        # Configuración base común
        config_base = {
            'smtp': config.get('smtp', {}),
            'ssh': config.get('ssh', {}),
            'remote_paths': config.get('remote_paths', {}),
            'timeouts': config.get('timeouts', {}),
            'backup': config.get('backup', {}),
            'system': config.get('system', {})
        }
        
        # Configuración específica del sistema
        if nombre_sistema in config:
            config_base.update(config[nombre_sistema])
        
        return config_base

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
            if os.path.exists(self.archivo_estado):
                import json
                with open(self.archivo_estado, 'r', encoding='utf-8') as f:
                    estado = json.load(f)
                    # Asegurar estructura básica
                    return self._migrar_estructura_estado(estado)
        except Exception as e:
            self.logger.warning(f"⚠️ Error cargando estado {self.archivo_estado}: {e}")
        
        return self._estado_por_defecto()
    
    def _migrar_estructura_estado(self, estado: Dict[str, Any]) -> Dict[str, Any]:
        """Migrar estructura antigua si es necesario"""
        # Estructura base común
        if 'estadisticas_migracion' not in estado:
            estado['estadisticas_migracion'] = {
                'exitosas': estado.get('migraciones_realizadas', 0),
                'fallidas': 0,
                'total_tiempo': 0
            }
        
        if 'backups_realizados' not in estado:
            estado['backups_realizados'] = 0
        
        return estado
    
    def _estado_por_defecto(self) -> Dict[str, Any]:
        """Estado por defecto para cualquier sistema"""
        return {
            'sistema': self.nombre_sistema,
            'db_inicializada': False,
            'fecha_inicializacion': None,
            'ultima_sincronizacion': None,
            'modo_operacion': 'remoto',  # Siempre remoto
            'ssh_conectado': False,
            'ssh_error': None,
            'ultima_verificacion': None,
            'estadisticas_migracion': {
                'exitosas': 0,
                'fallidas': 0,
                'total_tiempo': 0
            },
            'backups_realizados': 0,
            'version_estructura': '2.0'  # Nueva versión
        }
    
    def guardar_estado(self):
        """Guardar estado a archivo JSON"""
        try:
            import json
            with open(self.archivo_estado, 'w', encoding='utf-8') as f:
                json.dump(self.estado, f, indent=2, default=str)
            self.logger.debug(f"Estado guardado en {self.archivo_estado}")
        except Exception as e:
            self.logger.error(f"❌ Error guardando estado: {e}")
    
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
        from datetime import datetime
        return datetime.now().isoformat()
    
    def esta_inicializada(self) -> bool:
        """Verificar si la BD está inicializada"""
        return self.estado.get('db_inicializada', False)
    
    def obtener_fecha_inicializacion(self):
        """Obtener fecha de inicialización"""
        from datetime import datetime
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
# GESTOR DE CONEXIÓN SSH COMPARTIDO
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
        self.config = CargadorConfiguracion.obtener_config_sistema('system')
        self.logger = SistemaLogging.obtener_logger('ssh_shared')
        self.ssh_config = self.config.get('ssh', {})
        
        if not self.ssh_config.get('enabled', True):
            self.logger.warning("SSH deshabilitado en configuración")
    
    def conectar(self) -> bool:
        """Establecer conexión SSH con el servidor remoto"""
        try:
            import paramiko
            import socket
            
            if not self.ssh_config.get('host'):
                self.logger.error("No hay configuración SSH disponible")
                return False
            
            if self._ssh_client and self._verificar_conexion_activa():
                self.logger.debug("Conexión SSH ya activa, reutilizando")
                return True
            
            self.logger.info(f"🔗 Conectando SSH a {self.ssh_config['host']}:{self.ssh_config.get('port', 22)}...")
            
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            timeout = self.config.get('timeouts', {}).get('ssh_connect', 30)
            
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
            sftp_timeout = self.config.get('timeouts', {}).get('sftp_transfer', 300)
            self._sftp_client.get_channel().settimeout(sftp_timeout)
            
            self.logger.info(f"✅ Conexión SSH establecida a {self.ssh_config['host']}")
            return True
            
        except socket.timeout:
            self.logger.error(f"❌ Timeout conectando a {self.ssh_config.get('host', 'desconocido')}")
            return False
        except paramiko.AuthenticationException:
            self.logger.error("❌ Error de autenticación SSH - Credenciales incorrectas")
            return False
        except Exception as e:
            self.logger.error(f"❌ Error de conexión SSH: {str(e)}")
            return False
    
    def _verificar_conexion_activa(self) -> bool:
        """Verificar si la conexión SSH está activa"""
        try:
            if self._ssh_client and self._sftp_client:
                # Intentar un comando simple
                self._ssh_client.exec_command('pwd', timeout=5)
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
    
    def ejecutar_comando_remoto(self, comando: str, timeout: int = 30) -> tuple:
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
    def verificar_espacio_disco(ruta: str, espacio_minimo_mb: int = 100) -> tuple:
        """Verificar espacio disponible en disco"""
        try:
            import psutil
            stat = psutil.disk_usage(ruta)
            espacio_disponible_mb = stat.free / (1024 * 1024)
            
            if espacio_disponible_mb < espacio_minimo_mb:
                return False, espacio_disponible_mb
            
            return True, espacio_disponible_mb
            
        except Exception as e:
            return False, 0
    
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
    def crear_directorio_si_no_existe(ruta: str):
        """Crear directorio si no existe"""
        import os
        if not os.path.exists(ruta):
            os.makedirs(ruta, exist_ok=True)
            return True
        return False
    
    @staticmethod
    def generar_timestamp() -> str:
        """Generar timestamp para nombres de archivo"""
        from datetime import datetime
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
