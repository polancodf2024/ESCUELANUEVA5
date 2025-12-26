"""
aspirantes30.py - Sistema de Gestión de Aspirantes
Versión refactorizada con estado independiente
Sistema REMOTO exclusivo - Base de datos independiente
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta
import sqlite3
import tempfile
import hashlib
import bcrypt
import time
import re
from typing import Dict, Any, List, Optional
import sys

# Importar módulos compartidos
sys.path.insert(0, os.path.dirname(__file__))
from shared_config import (
    CargadorConfiguracion,
    SistemaLogging,
    EstadoPersistenteBase,
    GestorSSHCompartido,
    UtilidadesCompartidas
)

# =============================================================================
# CONFIGURACIÓN ESPECÍFICA DEL SISTEMA DE ASPIRANTES
# =============================================================================

class ConfiguracionAspirantes:
    """Configuración específica para el sistema de aspirantes"""
    
    def __init__(self):
        self.config = CargadorConfiguracion.obtener_config_sistema('aspirantes')
        self.ssh = GestorSSHCompartido()
        self.logger = SistemaLogging.obtener_logger(
            'aspirantes',
            self.config.get('log_file', 'aspirantes_detallado.log')
        )
        
        # Rutas específicas
        self.remote_paths = self.config.get('remote_paths', {})
        self.db_path_remoto = self.remote_paths.get('aspirantes_db', '')
        self.uploads_path_remoto = self.remote_paths.get('uploads_aspirantes', '')
        
        # Configuración del sistema
        self.estado_file = self.config.get('estado_file', 'estado_aspirantes.json')
        self.backup_dir = self.config.get('backup_dir', 'backups_aspirantes')
        self.sync_on_start = self.config.get('sync_on_start', True)
        self.auto_connect = self.config.get('auto_connect', True)
        
        self.logger.info("✅ Configuración de aspirantes cargada")

# =============================================================================
# ESTADO PERSISTENTE PARA ASPIRANTES
# =============================================================================

class EstadoAspirantes(EstadoPersistenteBase):
    """Estado persistente específico para aspirantes"""
    
    def __init__(self):
        config = CargadorConfiguracion.obtener_config_sistema('aspirantes')
        archivo_estado = config.get('estado_file', 'estado_aspirantes.json')
        super().__init__(archivo_estado, 'aspirantes')
    
    def _estado_por_defecto(self) -> Dict[str, Any]:
        """Estado por defecto específico para aspirantes"""
        estado_base = super()._estado_por_defecto()
        
        # Campos específicos para aspirantes
        estado_base.update({
            'total_aspirantes': 0,
            'aspirantes_activos': 0,
            'aspirantes_procesados': 0,
            'ultima_actualizacion': None,
            'categorias': ['Nuevo', 'En Revisión', 'Aprobado', 'Rechazado', 'Matriculado'],
            'programas_disponibles': [
                'Enfermería General',
                'Enfermería Pediátrica', 
                'Enfermería Geriátrica',
                'Enfermería Quirúrgica',
                'Enfermería Obstétrica'
            ]
        })
        
        return estado_base

# =============================================================================
# GESTOR DE BASE DE DATOS DE ASPIRANTES
# =============================================================================

class GestorBaseDatosAspirantes:
    """Gestor de base de datos específico para aspirantes"""
    
    def __init__(self, config: ConfiguracionAspirantes):
        self.config = config
        self.logger = config.logger
        self.ssh = config.ssh
        self.db_local_temp = None
        self.ultima_sincronizacion = None
        
        # Instanciar estado específico
        self.estado = EstadoAspirantes()
        
        # Intentar sincronización inicial si está configurado
        if config.sync_on_start and config.auto_connect:
            self._intentar_sincronizacion_inicial()
    
    def _intentar_sincronizacion_inicial(self):
        """Intentar sincronización inicial"""
        try:
            self.logger.info("🔄 Intentando sincronización inicial...")
            if self.sincronizar_desde_remoto():
                self.logger.info("✅ Sincronización inicial exitosa")
            else:
                self.logger.warning("⚠️ Sincronización inicial fallida")
        except Exception as e:
            self.logger.error(f"❌ Error en sincronización inicial: {e}")
    
    def sincronizar_desde_remoto(self) -> bool:
        """Sincronizar base de datos desde el servidor remoto"""
        try:
            self.logger.info("📥 Sincronizando base de datos de aspirantes desde remoto...")
            
            # Conectar SSH
            if not self.ssh.conectar():
                self.logger.error("❌ No se pudo conectar SSH")
                return False
            
            sftp = self.ssh.obtener_sftp()
            if not sftp:
                self.logger.error("❌ No se pudo obtener cliente SFTP")
                return False
            
            # Crear archivo temporal local
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.db_local_temp = os.path.join(temp_dir, f"aspirantes_temp_{timestamp}.db")
            
            # Verificar espacio en disco
            espacio_ok, espacio_mb = UtilidadesCompartidas.verificar_espacio_disco(temp_dir, 200)
            if not espacio_ok:
                self.logger.error(f"❌ Espacio en disco insuficiente: {espacio_mb:.1f} MB")
                return False
            
            # Descargar archivo remoto
            try:
                sftp.get(self.config.db_path_remoto, self.db_local_temp)
                
                # Verificar que se descargó correctamente
                if os.path.exists(self.db_local_temp) and os.path.getsize(self.db_local_temp) > 0:
                    self.ultima_sincronizacion = datetime.now()
                    file_size = os.path.getsize(self.db_local_temp)
                    self.logger.info(f"✅ Base de datos descargada: {file_size} bytes")
                    
                    # Si no existe la estructura, inicializarla
                    if not self._verificar_estructura_basica():
                        self.logger.info("📝 Inicializando estructura de base de datos...")
                        self._inicializar_estructura_db()
                    
                    # Actualizar estado
                    if not self.estado.esta_inicializada():
                        self.estado.marcar_db_inicializada()
                    self.estado.marcar_sincronizacion()
                    self.estado.set_ssh_conectado(True, None)
                    
                    return True
                else:
                    self.logger.warning("⚠️ Archivo descargado vacío, creando nueva base de datos")
                    return self._crear_nueva_db_remota()
                    
            except FileNotFoundError:
                self.logger.warning("⚠️ Base de datos no encontrada en servidor, creando nueva")
                return self._crear_nueva_db_remota()
                
        except Exception as e:
            self.logger.error(f"❌ Error sincronizando desde remoto: {e}")
            self.estado.set_ssh_conectado(False, str(e))
            return False
    
    def _verificar_estructura_basica(self) -> bool:
        """Verificar estructura básica de la base de datos"""
        try:
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                return False
            
            conn = sqlite3.connect(self.db_local_temp)
            cursor = conn.cursor()
            
            # Verificar tabla principal de aspirantes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aspirantes'")
            if cursor.fetchone():
                conn.close()
                return True
            
            conn.close()
            return False
            
        except Exception as e:
            self.logger.error(f"Error verificando estructura: {e}")
            return False
    
    def _crear_nueva_db_remota(self) -> bool:
        """Crear nueva base de datos en el servidor remoto"""
        try:
            self.logger.info("📝 Creando nueva base de datos de aspirantes...")
            
            # Crear archivo temporal
            temp_dir = tempfile.gettempdir()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_db = os.path.join(temp_dir, f"aspirantes_nueva_{timestamp}.db")
            
            # Inicializar estructura
            self._inicializar_estructura_db_completa(temp_db)
            
            # Subir al servidor
            if not self.ssh.conectar():
                return False
            
            sftp = self.ssh.obtener_sftp()
            if not sftp:
                return False
            
            # Crear directorio si no existe
            remote_dir = os.path.dirname(self.config.db_path_remoto)
            try:
                sftp.stat(remote_dir)
            except:
                self._crear_directorio_remoto_recursivo(remote_dir)
            
            # Subir archivo
            sftp.put(temp_db, self.config.db_path_remoto)
            
            # Actualizar referencia local
            self.db_local_temp = temp_db
            self.ultima_sincronizacion = datetime.now()
            
            # Actualizar estado
            self.estado.marcar_db_inicializada()
            self.estado.marcar_sincronizacion()
            self.estado.set_ssh_conectado(True, None)
            
            self.logger.info("✅ Nueva base de datos creada y subida al servidor")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error creando nueva base de datos: {e}")
            return False
    
    def _crear_directorio_remoto_recursivo(self, remote_path: str):
        """Crear directorio remoto recursivamente"""
        sftp = self.ssh.obtener_sftp()
        if not sftp:
            return
        
        try:
            sftp.stat(remote_path)
            self.logger.debug(f"Directorio remoto ya existe: {remote_path}")
        except:
            try:
                parent_dir = os.path.dirname(remote_path)
                if parent_dir and parent_dir != '/':
                    self._crear_directorio_remoto_recursivo(parent_dir)
                sftp.mkdir(remote_path)
                self.logger.info(f"✅ Directorio remoto creado: {remote_path}")
            except Exception as e:
                self.logger.error(f"Error creando directorio {remote_path}: {e}")
    
    def _inicializar_estructura_db_completa(self, db_path: str):
        """Inicializar estructura completa de la base de datos de aspirantes"""
        try:
            self.logger.info(f"📝 Inicializando estructura en: {db_path}")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Tabla de aspirantes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aspirantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folio TEXT UNIQUE NOT NULL,
                    nombre_completo TEXT NOT NULL,
                    email TEXT NOT NULL,
                    telefono TEXT,
                    fecha_nacimiento DATE,
                    genero TEXT,
                    direccion TEXT,
                    municipio TEXT,
                    estado TEXT,
                    cp TEXT,
                    programa_interes TEXT NOT NULL,
                    nivel_academico TEXT,
                    institucion_procedencia TEXT,
                    promedio_general REAL,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estatus TEXT DEFAULT 'Nuevo',
                    comentarios TEXT,
                    documentos_subidos INTEGER DEFAULT 0,
                    documentos_nombres TEXT,
                    documentos_rutas TEXT,
                    usuario_registro TEXT,
                    foto_ruta TEXT,
                    fecha_examen DATE,
                    puntaje_examen REAL,
                    entrevistador TEXT,
                    observaciones_entrevista TEXT,
                    fecha_decision DATE,
                    decision TEXT,
                    motivo_rechazo TEXT,
                    fecha_matriculacion DATE,
                    matricula_asignada TEXT,
                    usuario TEXT
                )
            ''')
            
            # Tabla de documentos de aspirantes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documentos_aspirantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folio_aspirante TEXT NOT NULL,
                    tipo_documento TEXT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    ruta_archivo TEXT NOT NULL,
                    tamaño INTEGER,
                    fecha_subida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    estatus TEXT DEFAULT 'ACTIVO',
                    observaciones TEXT,
                    usuario_subida TEXT
                )
            ''')
            
            # Tabla de bitácora de aspirantes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bitacora_aspirantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT NOT NULL,
                    accion TEXT NOT NULL,
                    modulo TEXT,
                    detalles TEXT,
                    ip TEXT,
                    user_agent TEXT,
                    resultado TEXT
                )
            ''')
            
            # Tabla de configuracion de aspirantes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS configuracion_aspirantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clave TEXT UNIQUE NOT NULL,
                    valor TEXT,
                    tipo TEXT,
                    descripcion TEXT,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Índices para rendimiento
            indices = [
                ('idx_aspirantes_folio', 'aspirantes(folio)'),
                ('idx_aspirantes_email', 'aspirantes(email)'),
                ('idx_aspirantes_estatus', 'aspirantes(estatus)'),
                ('idx_aspirantes_programa', 'aspirantes(programa_interes)'),
                ('idx_documentos_folio', 'documentos_aspirantes(folio_aspirante)'),
                ('idx_bitacora_usuario', 'bitacora_aspirantes(usuario)'),
                ('idx_bitacora_timestamp', 'bitacora_aspirantes(timestamp)')
            ]
            
            for nombre_idx, definicion in indices:
                try:
                    cursor.execute(f'CREATE INDEX IF NOT EXISTS {nombre_idx} ON {definicion}')
                except Exception as e:
                    self.logger.warning(f"⚠️ Error creando índice {nombre_idx}: {e}")
            
            # Insertar configuración inicial
            configuraciones = [
                ('version_sistema', '2.0', 'texto', 'Versión del sistema de aspirantes'),
                ('max_documentos_por_aspirante', '10', 'entero', 'Máximo de documentos por aspirante'),
                ('dias_retencion_documentos', '365', 'entero', 'Días de retención de documentos'),
                ('puntaje_minimo_aprobacion', '70', 'real', 'Puntaje mínimo para aprobación'),
                ('notificaciones_habilitadas', 'true', 'booleano', 'Notificaciones habilitadas')
            ]
            
            for clave, valor, tipo, descripcion in configuraciones:
                cursor.execute('''
                    INSERT OR REPLACE INTO configuracion_aspirantes (clave, valor, tipo, descripcion)
                    VALUES (?, ?, ?, ?)
                ''', (clave, valor, tipo, descripcion))
            
            conn.commit()
            conn.close()
            
            self.logger.info("✅ Estructura de base de datos de aspirantes inicializada")
            
        except Exception as e:
            self.logger.error(f"❌ Error inicializando estructura: {e}")
            raise
    
    def _inicializar_estructura_db(self):
        """Inicializar estructura en la base de datos local actual"""
        if not self.db_local_temp:
            return
        
        try:
            conn = sqlite3.connect(self.db_local_temp)
            cursor = conn.cursor()
            
            # Solo crear tabla de aspirantes si no existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='aspirantes'")
            if not cursor.fetchone():
                cursor.execute('''
                    CREATE TABLE aspirantes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        folio TEXT UNIQUE NOT NULL,
                        nombre_completo TEXT NOT NULL,
                        email TEXT NOT NULL,
                        telefono TEXT,
                        fecha_nacimiento DATE,
                        programa_interes TEXT NOT NULL,
                        nivel_academico TEXT,
                        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        estatus TEXT DEFAULT 'Nuevo',
                        documentos_subidos INTEGER DEFAULT 0
                    )
                ''')
                self.logger.info("✅ Tabla básica de aspirantes creada")
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error inicializando estructura básica: {e}")
    
    def sincronizar_hacia_remoto(self) -> bool:
        """Sincronizar cambios locales hacia el servidor remoto"""
        try:
            self.logger.info("📤 Sincronizando cambios hacia servidor remoto...")
            
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                self.logger.error("❌ No hay base de datos local para subir")
                return False
            
            # Conectar SSH
            if not self.ssh.conectar():
                return False
            
            sftp = self.ssh.obtener_sftp()
            if not sftp:
                return False
            
            # Crear backup antes de sobreescribir
            backup_config = self.config.config.get('backup', {})
            if backup_config.get('auto_backup_before_migration', True):
                try:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = f"{self.config.db_path_remoto}.backup_{timestamp}"
                    sftp.rename(self.config.db_path_remoto, backup_path)
                    self.logger.info(f"✅ Backup creado: {backup_path}")
                    self.estado.registrar_backup()
                except Exception as e:
                    self.logger.warning(f"⚠️ No se pudo crear backup: {e}")
            
            # Subir archivo
            sftp.put(self.db_local_temp, self.config.db_path_remoto)
            
            self.ultima_sincronizacion = datetime.now()
            self.estado.marcar_sincronizacion()
            
            self.logger.info("✅ Cambios subidos exitosamente al servidor")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error sincronizando hacia remoto: {e}")
            return False
    
    def obtener_conexion(self):
        """Obtener conexión a la base de datos local"""
        try:
            if not self.db_local_temp or not os.path.exists(self.db_local_temp):
                if not self.sincronizar_desde_remoto():
                    raise Exception("No se pudo sincronizar la base de datos")
            
            conn = sqlite3.connect(self.db_local_temp)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000")
            
            return conn
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo conexión: {e}")
            raise
    
    # =============================================================================
    # MÉTODOS DE CONSULTA Y OPERACIONES
    # =============================================================================
    
    def obtener_total_aspirantes(self) -> int:
        """Obtener total de aspirantes registrados"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM aspirantes")
                return cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error obteniendo total de aspirantes: {e}")
            return 0
    
    def obtener_aspirantes(self, pagina: int = 1, busqueda: str = "", estatus: str = "") -> tuple:
        """Obtener aspirantes con paginación y búsqueda"""
        try:
            tamano_pagina = 50
            offset = (pagina - 1) * tamano_pagina
            
            with self.obtener_conexion() as conn:
                condiciones = []
                parametros = []
                
                if busqueda:
                    condiciones.append("(folio LIKE ? OR nombre_completo LIKE ? OR email LIKE ?)")
                    parametros.extend([f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"])
                
                if estatus:
                    condiciones.append("estatus = ?")
                    parametros.append(estatus)
                
                where_clause = " AND ".join(condiciones) if condiciones else "1=1"
                
                # Consulta principal
                query = f"""
                    SELECT * FROM aspirantes 
                    WHERE {where_clause}
                    ORDER BY fecha_registro DESC 
                    LIMIT ? OFFSET ?
                """
                parametros.extend([tamano_pagina, offset])
                
                df = pd.read_sql_query(query, conn, params=parametros)
                
                # Total de registros
                count_query = f"SELECT COUNT(*) FROM aspirantes WHERE {where_clause}"
                count_params = parametros[:-2] if len(parametros) > 2 else []
                
                total = pd.read_sql_query(count_query, conn, params=count_params).iloc[0, 0]
                total_paginas = max(1, (total + tamano_pagina - 1) // tamano_pagina)
                
                self.logger.debug(f"Obtenidos {len(df)} aspirantes (página {pagina}/{total_paginas})")
                
                # Actualizar estadísticas en estado
                if pagina == 1 and not busqueda and not estatus:
                    self.estado.estado['total_aspirantes'] = total
                    self.estado.estado['ultima_actualizacion'] = datetime.now().isoformat()
                    self.estado.guardar_estado()
                
                return df, total_paginas, total
                
        except Exception as e:
            self.logger.error(f"Error obteniendo aspirantes: {e}")
            return pd.DataFrame(), 0, 0
    
    def registrar_aspirante(self, datos: Dict[str, Any]) -> Optional[int]:
        """Registrar nuevo aspirante"""
        try:
            # Generar folio único
            timestamp = datetime.now().strftime('%y%m%d')
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM aspirantes WHERE folio LIKE ?", 
                             (f"ASP-{timestamp}-%",))
                consecutivo = cursor.fetchone()[0] + 1
                folio = f"ASP-{timestamp}-{consecutivo:03d}"
            
            datos['folio'] = folio
            datos['fecha_registro'] = datetime.now()
            datos['fecha_actualizacion'] = datetime.now()
            
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                
                columnas = []
                valores = []
                placeholders = []
                
                for columna, valor in datos.items():
                    if valor is not None:
                        columnas.append(columna)
                        valores.append(valor)
                        placeholders.append('?')
                
                query = f"INSERT INTO aspirantes ({', '.join(columnas)}) VALUES ({', '.join(placeholders)})"
                cursor.execute(query, valores)
                aspirante_id = cursor.lastrowid
                
                conn.commit()
                
                # Registrar en bitácora
                cursor.execute('''
                    INSERT INTO bitacora_aspirantes (usuario, accion, detalles, resultado)
                    VALUES (?, ?, ?, ?)
                ''', (
                    datos.get('usuario_registro', 'sistema'),
                    'REGISTRO_ASPIRANTE',
                    f"Nuevo aspirante registrado: {folio} - {datos.get('nombre_completo', '')}",
                    'EXITO'
                ))
                
                self.logger.info(f"✅ Aspirante registrado: {folio}")
                return aspirante_id
                
        except Exception as e:
            self.logger.error(f"❌ Error registrando aspirante: {e}")
            return None
    
    def actualizar_estatus_aspirante(self, folio: str, nuevo_estatus: str, usuario: str = "", observaciones: str = "") -> bool:
        """Actualizar estatus de un aspirante"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                
                # Actualizar estatus
                cursor.execute('''
                    UPDATE aspirantes 
                    SET estatus = ?, fecha_actualizacion = CURRENT_TIMESTAMP,
                        fecha_decision = CASE WHEN ? IN ('Aprobado', 'Rechazado', 'Matriculado') THEN CURRENT_DATE ELSE fecha_decision END,
                        decision = CASE WHEN ? IN ('Aprobado', 'Rechazado', 'Matriculado') THEN ? ELSE decision END
                    WHERE folio = ?
                ''', (nuevo_estatus, nuevo_estatus, nuevo_estatus, nuevo_estatus, folio))
                
                if cursor.rowcount == 0:
                    self.logger.warning(f"Aspirante no encontrado: {folio}")
                    return False
                
                # Registrar en bitácora
                cursor.execute('''
                    INSERT INTO bitacora_aspirantes (usuario, accion, detalles, resultado)
                    VALUES (?, ?, ?, ?)
                ''', (
                    usuario or 'sistema',
                    'CAMBIO_ESTATUS',
                    f"Aspirante {folio}: {nuevo_estatus} - {observaciones}",
                    'EXITO'
                ))
                
                conn.commit()
                
                self.logger.info(f"✅ Estatus actualizado: {folio} -> {nuevo_estatus}")
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Error actualizando estatus: {e}")
            return False
    
    def asignar_matricula(self, folio: str, matricula: str, usuario: str = "") -> bool:
        """Asignar matrícula a aspirante aprobado"""
        try:
            with self.obtener_conexion() as conn:
                cursor = conn.cursor()
                
                # Verificar que el aspirante existe y está aprobado
                cursor.execute("SELECT estatus FROM aspirantes WHERE folio = ?", (folio,))
                resultado = cursor.fetchone()
                
                if not resultado:
                    self.logger.warning(f"Aspirante no encontrado: {folio}")
                    return False
                
                if resultado[0] != 'Aprobado':
                    self.logger.warning(f"Aspirante {folio} no está aprobado (estatus: {resultado[0]})")
                    return False
                
                # Actualizar con matrícula y cambiar estatus
                cursor.execute('''
                    UPDATE aspirantes 
                    SET matricula_asignada = ?, 
                        estatus = 'Matriculado',
                        fecha_matriculacion = CURRENT_DATE,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE folio = ?
                ''', (matricula, folio))
                
                # Registrar en bitácora
                cursor.execute('''
                    INSERT INTO bitacora_aspirantes (usuario, accion, detalles, resultado)
                    VALUES (?, ?, ?, ?)
                ''', (
                    usuario or 'sistema',
                    'ASIGNACION_MATRICULA',
                    f"Aspirante {folio} matriculado con matrícula: {matricula}",
                    'EXITO'
                ))
                
                conn.commit()
                
                # Actualizar estadísticas
                self.estado.estado['aspirantes_procesados'] = self.estado.estado.get('aspirantes_procesados', 0) + 1
                self.estado.guardar_estado()
                
                self.logger.info(f"✅ Matrícula asignada: {folio} -> {matricula}")
                return True
                
        except Exception as e:
            self.logger.error(f"❌ Error asignando matrícula: {e}")
            return False

# =============================================================================
# INTERFAZ DE USUARIO PARA ASPIRANTES
# =============================================================================

class InterfazAspirantes:
    """Interfaz de usuario para el sistema de aspirantes"""
    
    def __init__(self):
        self.config = ConfiguracionAspirantes()
        self.gestor_db = GestorBaseDatosAspirantes(self.config)
        self.estado = self.gestor_db.estado
        self.logger = self.config.logger
        
        # Configurar página de Streamlit
        st.set_page_config(
            page_title="Sistema de Gestión de Aspirantes",
            page_icon="🎓",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Inicializar estado de sesión
        self._inicializar_estado_sesion()
    
    def _inicializar_estado_sesion(self):
        """Inicializar estado de sesión de Streamlit"""
        defaults = {
            'login_exitoso': False,
            'usuario_actual': None,
            'rol_usuario': None,
            'pagina_actual': 1,
            'termino_busqueda': '',
            'filtro_estatus': '',
            'aspirante_seleccionado': None
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def mostrar_sidebar(self):
        """Mostrar sidebar con información del sistema"""
        with st.sidebar:
            st.title("🎓 Sistema de Aspirantes")
            st.markdown("---")
            
            # Estado del sistema
            st.subheader("🔧 Estado del Sistema")
            
            col1, col2 = st.columns(2)
            with col1:
                if self.estado.esta_inicializada():
                    st.success("✅ Inicializada")
                else:
                    st.warning("⚠️ No inicializada")
            
            with col2:
                if self.estado.estado.get('ssh_conectado'):
                    st.success("✅ SSH Conectado")
                else:
                    st.error("❌ SSH Desconectado")
            
            # Estadísticas
            st.subheader("📊 Estadísticas")
            st.metric("Total Aspirantes", self.estado.estado.get('total_aspirantes', 0))
            st.metric("Procesados", self.estado.estado.get('aspirantes_procesados', 0))
            
            # Fecha última actualización
            ultima_actualizacion = self.estado.estado.get('ultima_actualizacion')
            if ultima_actualizacion:
                try:
                    fecha = datetime.fromisoformat(ultima_actualizacion)
                    st.caption(f"🔄 Actualizado: {fecha.strftime('%H:%M:%S')}")
                except:
                    pass
            
            st.markdown("---")
            
            # Controles del sistema
            st.subheader("⚙️ Controles")
            
            if st.button("🔄 Sincronizar Ahora", use_container_width=True):
                with st.spinner("Sincronizando..."):
                    if self.gestor_db.sincronizar_desde_remoto():
                        st.success("✅ Sincronización exitosa")
                        st.rerun()
                    else:
                        st.error("❌ Error sincronizando")
            
            if st.button("📊 Actualizar Estadísticas", use_container_width=True):
                total = self.gestor_db.obtener_total_aspirantes()
                self.estado.estado['total_aspirantes'] = total
                self.estado.guardar_estado()
                st.success(f"✅ Estadísticas actualizadas: {total} aspirantes")
                st.rerun()
            
            # Información del sistema
            with st.expander("ℹ️ Información del Sistema"):
                st.write(f"**Sistema:** Aspirantes")
                st.write(f"**Versión:** 2.0")
                st.write(f"**Base de datos:** {os.path.basename(self.config.db_path_remoto)}")
                st.write(f"**Modo:** Remoto exclusivo")
                
                if self.gestor_db.db_local_temp and os.path.exists(self.gestor_db.db_local_temp):
                    size = os.path.getsize(self.gestor_db.db_local_temp)
                    st.write(f"**Tamaño local:** {size/1024:.1f} KB")
    
    def mostrar_login(self):
        """Mostrar interfaz de login"""
        st.title("🎓 Sistema de Gestión de Aspirantes")
        st.markdown("---")
        
        # Mostrar estado actual
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if self.estado.esta_inicializada():
                st.success("✅ Base de datos inicializada")
            else:
                st.warning("⚠️ Base de datos NO inicializada")
        
        with col2:
            if self.estado.estado.get('ssh_conectado'):
                st.success("✅ SSH Conectado")
            else:
                st.error("❌ SSH Desconectado")
        
        with col3:
            temp_dir = tempfile.gettempdir()
            espacio_ok, espacio_mb = UtilidadesCompartidas.verificar_espacio_disco(temp_dir)
            if espacio_ok:
                st.success(f"💾 {espacio_mb:.0f} MB")
            else:
                st.warning(f"💾 {espacio_mb:.0f} MB")
        
        st.markdown("---")
        
        # Formulario de login/inicialización
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form_aspirantes"):
                st.subheader("Acceso al Sistema de Aspirantes")
                
                # Para el sistema de aspirantes, uso credenciales simples
                usuario = st.text_input("👤 Usuario", value="admin", key="usuario_aspirantes")
                password = st.text_input("🔒 Contraseña", type="password", value="admin123", key="password_aspirantes")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    login_btn = st.form_submit_button("🚀 Iniciar Sesión", use_container_width=True)
                with col_b:
                    init_btn = st.form_submit_button("🔄 Inicializar DB", use_container_width=True, type="secondary")
                
                if login_btn:
                    if usuario == "admin" and password == "admin123":
                        st.session_state.login_exitoso = True
                        st.session_state.usuario_actual = {"usuario": "admin", "rol": "administrador"}
                        st.session_state.rol_usuario = "administrador"
                        st.success("✅ ¡Bienvenido al sistema de aspirantes!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas")
                
                if init_btn:
                    with st.spinner("Inicializando base de datos de aspirantes en servidor remoto..."):
                        if self.gestor_db.sincronizar_desde_remoto():
                            st.success("✅ Base de datos de aspirantes inicializada")
                            st.info("Ahora puedes iniciar sesión con:")
                            st.info("👤 Usuario: admin")
                            st.info("🔒 Contraseña: admin123")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Error inicializando base de datos")
    
    def mostrar_panel_principal(self):
        """Mostrar panel principal después del login"""
        # Barra superior
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        
        with col1:
            st.title("🎓 Sistema de Gestión de Aspirantes")
            st.write(f"**👤 Usuario:** {st.session_state.usuario_actual.get('usuario', 'admin')}")
        
        with col2:
            total = self.estado.estado.get('total_aspirantes', 0)
            st.metric("Total Aspirantes", total)
        
        with col3:
            if st.button("🔄 Recargar", use_container_width=True):
                st.rerun()
        
        with col4:
            if st.button("🚪 Salir", use_container_width=True):
                st.session_state.login_exitoso = False
                st.session_state.usuario_actual = None
                st.rerun()
        
        st.markdown("---")
        
        # Pestañas principales
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Lista de Aspirantes", 
            "➕ Nuevo Aspirante", 
            "📊 Estadísticas",
            "⚙️ Configuración"
        ])
        
        with tab1:
            self._mostrar_lista_aspirantes()
        
        with tab2:
            self._mostrar_formulario_nuevo_aspirante()
        
        with tab3:
            self._mostrar_estadisticas()
        
        with tab4:
            self._mostrar_configuracion()
    
    def _mostrar_lista_aspirantes(self):
        """Mostrar lista de aspirantes con filtros"""
        st.subheader("📋 Lista de Aspirantes")
        
        # Filtros de búsqueda
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            busqueda = st.text_input(
                "🔍 Buscar por folio, nombre o email:",
                value=st.session_state.termino_busqueda,
                key="busqueda_aspirantes"
            )
            if busqueda != st.session_state.termino_busqueda:
                st.session_state.termino_busqueda = busqueda
                st.session_state.pagina_actual = 1
                st.rerun()
        
        with col2:
            estatus_opciones = ['', 'Nuevo', 'En Revisión', 'Aprobado', 'Rechazado', 'Matriculado']
            filtro_estatus = st.selectbox(
                "Filtrar por estatus:",
                options=estatus_opciones,
                index=estatus_opciones.index(st.session_state.filtro_estatus) if st.session_state.filtro_estatus in estatus_opciones else 0,
                key="filtro_estatus"
            )
            if filtro_estatus != st.session_state.filtro_estatus:
                st.session_state.filtro_estatus = filtro_estatus
                st.session_state.pagina_actual = 1
                st.rerun()
        
        with col3:
            st.write("")  # Espacio vertical
            if st.button("🧹 Limpiar Filtros", use_container_width=True):
                st.session_state.termino_busqueda = ''
                st.session_state.filtro_estatus = ''
                st.session_state.pagina_actual = 1
                st.rerun()
        
        # Obtener datos
        with st.spinner("Cargando aspirantes..."):
            df, total_paginas, total = self.gestor_db.obtener_aspirantes(
                pagina=st.session_state.pagina_actual,
                busqueda=st.session_state.termino_busqueda,
                estatus=st.session_state.filtro_estatus
            )
        
        # Mostrar resultados
        if df.empty:
            st.info("📭 No hay aspirantes registrados con los criterios de búsqueda")
            
            if st.session_state.termino_busqueda or st.session_state.filtro_estatus:
                if st.button("Ver todos los aspirantes"):
                    st.session_state.termino_busqueda = ''
                    st.session_state.filtro_estatus = ''
                    st.session_state.pagina_actual = 1
                    st.rerun()
        else:
            # Mostrar tabla
            st.dataframe(
                df[['folio', 'nombre_completo', 'email', 'programa_interes', 'estatus', 'fecha_registro']],
                use_container_width=True,
                hide_index=True
            )
            
            # Controles de paginación
            col_prev, col_page, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if st.session_state.pagina_actual > 1:
                    if st.button("⬅️ Anterior", use_container_width=True):
                        st.session_state.pagina_actual -= 1
                        st.rerun()
            
            with col_page:
                st.write(f"**Página {st.session_state.pagina_actual} de {total_paginas}**")
                st.caption(f"Mostrando {len(df)} de {total} aspirantes")
            
            with col_next:
                if st.session_state.pagina_actual < total_paginas:
                    if st.button("Siguiente ➡️", use_container_width=True):
                        st.session_state.pagina_actual += 1
                        st.rerun()
            
            # Detalles del aspirante seleccionado
            st.subheader("👤 Detalles del Aspirante")
            
            if not df.empty:
                # Seleccionar aspirante
                opciones = [f"{row['folio']} | {row['nombre_completo']} | {row['estatus']}" 
                          for _, row in df.iterrows()]
                
                seleccion = st.selectbox(
                    "Seleccione un aspirante para ver detalles:",
                    options=opciones,
                    key="seleccion_aspirante"
                )
                
                if seleccion:
                    folio = seleccion.split(' | ')[0]
                    aspirante = df[df['folio'] == folio].iloc[0]
                    
                    # Mostrar detalles en columnas
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Información Personal:**")
                        st.write(f"**Folio:** {aspirante['folio']}")
                        st.write(f"**Nombre:** {aspirante['nombre_completo']}")
                        st.write(f"**Email:** {aspirante['email']}")
                        st.write(f"**Teléfono:** {aspirante.get('telefono', 'No registrado')}")
                        st.write(f"**Fecha Nacimiento:** {aspirante.get('fecha_nacimiento', 'No registrada')}")
                        st.write(f"**Género:** {aspirante.get('genero', 'No especificado')}")
                    
                    with col2:
                        st.write("**Información Académica:**")
                        st.write(f"**Programa de Interés:** {aspirante['programa_interes']}")
                        st.write(f"**Nivel Académico:** {aspirante.get('nivel_academico', 'No especificado')}")
                        st.write(f"**Institución Procedencia:** {aspirante.get('institucion_procedencia', 'No especificada')}")
                        st.write(f"**Promedio:** {aspirante.get('promedio_general', 'No registrado')}")
                        st.write(f"**Estatus:** {aspirante['estatus']}")
                        st.write(f"**Fecha Registro:** {aspirante['fecha_registro']}")
                    
                    # Acciones según estatus
                    st.subheader("🔄 Acciones")
                    
                    if aspirante['estatus'] == 'Nuevo':
                        col_a1, col_a2 = st.columns(2)
                        with col_a1:
                            if st.button("📝 Marcar como 'En Revisión'", use_container_width=True):
                                if self.gestor_db.actualizar_estatus_aspirante(
                                    folio, 'En Revisión', 
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    "Cambio a revisión manual"
                                ):
                                    st.success("✅ Aspirante marcado para revisión")
                                    time.sleep(1)
                                    st.rerun()
                        
                        with col_a2:
                            if st.button("✅ Aprobar Directamente", type="primary", use_container_width=True):
                                if self.gestor_db.actualizar_estatus_aspirante(
                                    folio, 'Aprobado',
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    "Aprobación directa"
                                ):
                                    st.success("✅ Aspirante aprobado")
                                    time.sleep(1)
                                    st.rerun()
                    
                    elif aspirante['estatus'] == 'En Revisión':
                        col_b1, col_b2, col_b3 = st.columns(3)
                        with col_b1:
                            if st.button("✅ Aprobar", type="primary", use_container_width=True):
                                if self.gestor_db.actualizar_estatus_aspirante(
                                    folio, 'Aprobado',
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    "Aprobado tras revisión"
                                ):
                                    st.success("✅ Aspirante aprobado")
                                    time.sleep(1)
                                    st.rerun()
                        
                        with col_b2:
                            if st.button("❌ Rechazar", use_container_width=True):
                                motivo = st.text_input("Motivo del rechazo:", key=f"motivo_{folio}")
                                if st.button("Confirmar Rechazo", key=f"confirmar_{folio}"):
                                    if self.gestor_db.actualizar_estatus_aspirante(
                                        folio, 'Rechazado',
                                        st.session_state.usuario_actual.get('usuario', 'admin'),
                                        f"Rechazado: {motivo}"
                                    ):
                                        st.success("✅ Aspirante rechazado")
                                        time.sleep(1)
                                        st.rerun()
                        
                        with col_b3:
                            if st.button("↩️ Volver a 'Nuevo'", use_container_width=True):
                                if self.gestor_db.actualizar_estatus_aspirante(
                                    folio, 'Nuevo',
                                    st.session_state.usuario_actual.get('usuario', 'admin'),
                                    "Devuelto a estado inicial"
                                ):
                                    st.success("✅ Aspirante devuelto a estado inicial")
                                    time.sleep(1)
                                    st.rerun()
                    
                    elif aspirante['estatus'] == 'Aprobado':
                        st.info("✅ Este aspirante ha sido aprobado y está listo para matrícula.")
                        
                        # Asignar matrícula
                        matricula = st.text_input("Matrícula a asignar:", 
                                                placeholder="MAT-EST-2024001",
                                                key=f"matricula_{folio}")
                        
                        if st.button("🎓 Asignar Matrícula y Matricular", type="primary"):
                            if matricula and self.gestor_db.asignar_matricula(
                                folio, matricula,
                                st.session_state.usuario_actual.get('usuario', 'admin')
                            ):
                                st.success(f"✅ Matrícula {matricula} asignada y aspirante matriculado")
                                time.sleep(1)
                                st.rerun()
                            elif not matricula:
                                st.error("❌ Debe ingresar una matrícula")
    
    def _mostrar_formulario_nuevo_aspirante(self):
        """Mostrar formulario para nuevo aspirante"""
        st.subheader("➕ Registrar Nuevo Aspirante")
        
        with st.form("formulario_nuevo_aspirante"):
            st.write("Complete la información del nuevo aspirante:")
            
            col1, col2 = st.columns(2)
            
            with col1:
                nombre_completo = st.text_input("Nombre Completo *", placeholder="Juan Pérez López")
                email = st.text_input("Email *", placeholder="juan.perez@ejemplo.com")
                telefono = st.text_input("Teléfono", placeholder="5551234567")
                fecha_nacimiento = st.date_input("Fecha de Nacimiento", 
                                                value=datetime.now() - timedelta(days=365*18))
                genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro", "Prefiero no decir"])
                direccion = st.text_input("Dirección")
                municipio = st.text_input("Municipio")
            
            with col2:
                estado = st.text_input("Estado")
                cp = st.text_input("Código Postal")
                programa_interes = st.selectbox("Programa de Interés *", 
                                              self.estado.estado.get('programas_disponibles', []))
                nivel_academico = st.selectbox("Nivel Académico", 
                                             ["Bachillerato", "Licenciatura", "Técnico", "Otro"])
                institucion_procedencia = st.text_input("Institución de Procedencia")
                promedio_general = st.number_input("Promedio General", min_value=0.0, max_value=10.0, value=8.0, step=0.1)
                comentarios = st.text_area("Comentarios adicionales")
            
            submitted = st.form_submit_button("💾 Registrar Aspirante", type="primary")
            
            if submitted:
                # Validaciones
                if not nombre_completo or not email or not programa_interes:
                    st.error("❌ Los campos marcados con * son obligatorios")
                    return
                
                if not UtilidadesCompartidas.validar_email(email):
                    st.error("❌ Formato de email inválido")
                    return
                
                # Preparar datos
                datos_aspirante = {
                    'nombre_completo': nombre_completo,
                    'email': email,
                    'telefono': telefono,
                    'fecha_nacimiento': fecha_nacimiento,
                    'genero': genero,
                    'direccion': direccion,
                    'municipio': municipio,
                    'estado': estado,
                    'cp': cp,
                    'programa_interes': programa_interes,
                    'nivel_academico': nivel_academico,
                    'institucion_procedencia': institucion_procedencia,
                    'promedio_general': promedio_general,
                    'comentarios': comentarios,
                    'usuario_registro': st.session_state.usuario_actual.get('usuario', 'admin'),
                    'usuario': st.session_state.usuario_actual.get('usuario', 'admin')
                }
                
                with st.spinner("Registrando aspirante..."):
                    aspirante_id = self.gestor_db.registrar_aspirante(datos_aspirante)
                    
                    if aspirante_id:
                        st.success("✅ Aspirante registrado exitosamente")
                        
                        # Sincronizar cambios
                        if self.gestor_db.sincronizar_hacia_remoto():
                            st.success("✅ Cambios sincronizados con servidor remoto")
                        
                        # Resetear formulario después de 2 segundos
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("❌ Error registrando aspirante")
    
    def _mostrar_estadisticas(self):
        """Mostrar estadísticas del sistema"""
        st.subheader("📊 Estadísticas del Sistema")
        
        # Obtener datos estadísticos
        with self.gestor_db.obtener_conexion() as conn:
            # Estadísticas por estatus
            query_estatus = """
                SELECT estatus, COUNT(*) as cantidad 
                FROM aspirantes 
                GROUP BY estatus 
                ORDER BY cantidad DESC
            """
            df_estatus = pd.read_sql_query(query_estatus, conn)
            
            # Estadísticas por programa
            query_programa = """
                SELECT programa_interes, COUNT(*) as cantidad 
                FROM aspirantes 
                GROUP BY programa_interes 
                ORDER BY cantidad DESC
            """
            df_programa = pd.read_sql_query(query_programa, conn)
            
            # Registros por mes
            query_mensual = """
                SELECT strftime('%Y-%m', fecha_registro) as mes, COUNT(*) as cantidad 
                FROM aspirantes 
                GROUP BY mes 
                ORDER BY mes DESC 
                LIMIT 12
            """
            df_mensual = pd.read_sql_query(query_mensual, conn)
        
        # Mostrar métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total = self.estado.estado.get('total_aspirantes', 0)
            st.metric("Total Aspirantes", total)
        
        with col2:
            aprobados = df_estatus[df_estatus['estatus'] == 'Aprobado']['cantidad'].sum() if not df_estatus.empty else 0
            st.metric("Aprobados", aprobados)
        
        with col3:
            matriculados = df_estatus[df_estatus['estatus'] == 'Matriculado']['cantidad'].sum() if not df_estatus.empty else 0
            st.metric("Matriculados", matriculados)
        
        with col4:
            tasa_conversion = (matriculados / total * 100) if total > 0 else 0
            st.metric("Tasa Conversión", f"{tasa_conversion:.1f}%")
        
        st.markdown("---")
        
        # Gráficos
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            if not df_estatus.empty:
                st.subheader("📈 Distribución por Estatus")
                st.bar_chart(df_estatus.set_index('estatus'))
            else:
                st.info("No hay datos de estatus disponibles")
        
        with col_chart2:
            if not df_programa.empty:
                st.subheader("🎯 Programas Más Solicitados")
                st.bar_chart(df_programa.set_index('programa_interes'))
            else:
                st.info("No hay datos de programas disponibles")
        
        # Tabla mensual
        st.subheader("📅 Registros Mensuales")
        if not df_mensual.empty:
            st.dataframe(df_mensual, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos mensuales disponibles")
        
        # Exportar datos
        st.markdown("---")
        st.subheader("📤 Exportar Datos")
        
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            if st.button("📊 Exportar a Excel", use_container_width=True):
                # Crear Excel con todas las estadísticas
                import io
                buffer = io.BytesIO()
                
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df_estatus.to_excel(writer, sheet_name='Por Estatus', index=False)
                    df_programa.to_excel(writer, sheet_name='Por Programa', index=False)
                    df_mensual.to_excel(writer, sheet_name='Mensual', index=False)
                
                buffer.seek(0)
                
                st.download_button(
                    label="⬇️ Descargar Excel",
                    data=buffer,
                    file_name=f"estadisticas_aspirantes_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        with col_exp2:
            if st.button("📋 Exportar Lista Completa", use_container_width=True):
                with self.gestor_db.obtener_conexion() as conn:
                    df_completo = pd.read_sql_query("SELECT * FROM aspirantes", conn)
                
                st.download_button(
                    label="⬇️ Descargar CSV",
                    data=df_completo.to_csv(index=False).encode('utf-8'),
                    file_name=f"aspirantes_completo_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    def _mostrar_configuracion(self):
        """Mostrar configuración del sistema"""
        st.subheader("⚙️ Configuración del Sistema")
        
        # Información del sistema
        with st.expander("ℹ️ Información del Sistema"):
            st.write(f"**Nombre del sistema:** Aspirantes")
            st.write(f"**Versión:** 2.0")
            st.write(f"**Base de datos remota:** {self.config.db_path_remoto}")
            st.write(f"**Estado actual:** {'✅ Inicializado' if self.estado.esta_inicializada() else '⚠️ No inicializado'}")
            
            if self.gestor_db.db_local_temp:
                if os.path.exists(self.gestor_db.db_local_temp):
                    size = os.path.getsize(self.gestor_db.db_local_temp)
                    st.write(f"**Base de datos local:** {self.gestor_db.db_local_temp} ({size/1024:.1f} KB)")
            
            st.write(f"**Última sincronización:** {self.gestor_db.ultima_sincronizacion or 'No sincronizado'}")
        
        # Configuración de programas
        with st.expander("🎓 Programas Disponibles"):
            programas = self.estado.estado.get('programas_disponibles', [])
            st.write("Programas actuales:")
            for programa in programas:
                st.write(f"- {programa}")
            
            nuevo_programa = st.text_input("Agregar nuevo programa:")
            if st.button("➕ Agregar Programa"):
                if nuevo_programa and nuevo_programa not in programas:
                    programas.append(nuevo_programa)
                    self.estado.estado['programas_disponibles'] = programas
                    self.estado.guardar_estado()
                    st.success(f"✅ Programa '{nuevo_programa}' agregado")
                    st.rerun()
        
        # Mantenimiento del sistema
        with st.expander("🔧 Herramientas de Mantenimiento"):
            st.warning("⚠️ Estas acciones pueden afectar el sistema")
            
            col_m1, col_m2 = st.columns(2)
            
            with col_m1:
                if st.button("🔄 Forzar Sincronización", use_container_width=True):
                    with st.spinner("Sincronizando..."):
                        if self.gestor_db.sincronizar_desde_remoto():
                            st.success("✅ Sincronización forzada exitosa")
                        else:
                            st.error("❌ Error en sincronización forzada")
            
            with col_m2:
                if st.button("🗑️ Limpiar Cache Temporal", use_container_width=True):
                    if self.gestor_db.db_local_temp and os.path.exists(self.gestor_db.db_local_temp):
                        try:
                            os.remove(self.gestor_db.db_local_temp)
                            st.success("✅ Cache temporal limpiado")
                            self.gestor_db.db_local_temp = None
                        except Exception as e:
                            st.error(f"❌ Error limpiando cache: {e}")
                    else:
                        st.info("ℹ️ No hay cache temporal para limpiar")
            
            # Recrear base de datos
            if st.button("🆕 Recrear Base de Datos", type="secondary", use_container_width=True):
                st.error("🚨 Esta acción eliminará todos los datos y creará una nueva base de datos vacía")
                confirmacion = st.text_input("Escriba 'CONFIRMAR' para proceder:")
                
                if st.button("🚨 Ejecutar Recreación", type="primary", disabled=(confirmacion != "CONFIRMAR")):
                    with st.spinner("Recreando base de datos..."):
                        if self.gestor_db._crear_nueva_db_remota():
                            st.success("✅ Base de datos recreada exitosamente")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error("❌ Error recreando base de datos")
    
    def ejecutar(self):
        """Ejecutar la interfaz principal"""
        try:
            # Mostrar sidebar siempre
            self.mostrar_sidebar()
            
            # Mostrar contenido principal según estado
            if not st.session_state.login_exitoso:
                self.mostrar_login()
            else:
                self.mostrar_panel_principal()
                
        except Exception as e:
            st.error(f"❌ Error crítico en la aplicación: {str(e)}")
            self.logger.error(f"Error en interfaz: {e}", exc_info=True)
            
            with st.expander("🔧 Información de diagnóstico"):
                st.write("**Estado del sistema:**")
                st.json(self.estado.estado)
                
                st.write("**Configuración SSH:**")
                st.write(self.config.ssh_config)
                
                if self.gestor_db.db_local_temp:
                    st.write(f"**Base de datos local:** {self.gestor_db.db_local_temp}")
                    st.write(f"**Existe:** {os.path.exists(self.gestor_db.db_local_temp)}")

# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal del sistema de aspirantes"""
    try:
        # Inicializar y ejecutar interfaz
        app = InterfazAspirantes()
        app.ejecutar()
        
    except Exception as e:
        st.error(f"❌ Error fatal en el sistema de aspirantes: {e}")
        
        # Intentar logging si es posible
        try:
            logger = SistemaLogging.obtener_logger('aspirantes_critico')
            logger.critical(f"Error fatal en main(): {e}", exc_info=True)
        except:
            pass

if __name__ == "__main__":
    main()
