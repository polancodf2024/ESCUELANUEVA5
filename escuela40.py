"""
escuela40.py - Sistema de Gestión de Escuela (Refactorizado)
Versión 3.0 corregida para Streamlit Cloud
Sistema REMOTO exclusivo para gestión de estudiantes, inscritos, egresados, contratados
"""

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
import sys
import json
import time
from datetime import datetime, timedelta
import io
import hashlib
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Importar módulos compartidos - CORREGIDO PARA STREAMLIT CLOUD
try:
    from shared_config import (
        SistemaLogging,
        CargadorConfiguracion,
        EstadoPersistenteBase,
        GestorSSHCompartido,
        UtilidadesCompartidas
    )
    IMPORTACIONES_COMPLETAS = True
except ImportError as e:
    IMPORTACIONES_COMPLETAS = False
    st.error(f"❌ Error crítico: No se pudo importar módulos compartidos: {e}")
    st.info("⚠️ Verifica que shared_config.py esté en el mismo directorio")
    st.stop()

# =============================================================================
# CONFIGURACIÓN Y LOGGING - CORREGIDO
# =============================================================================

# Obtener configuración para el sistema escuela
try:
    config = CargadorConfiguracion.obtener_config_sistema('escuela')
    
    # Validar configuración básica
    if not config.get('ssh', {}).get('host') and config.get('ssh', {}).get('enabled', False):
        st.warning("⚠️ SSH habilitado pero no hay host configurado")
        config['ssh']['enabled'] = False
        
except Exception as e:
    st.error(f"❌ Error cargando configuración: {e}")
    # Configuración de emergencia
    config = {
        'estado_file': 'estado_escuela.json',
        'log_file': 'escuela_detallado.log',
        'page_size': 50,
        'cache_ttl': 300,
        'ssh': {'enabled': False},
        'remote_paths': {},
        'backup': {'enabled': False},
        'sync_on_start': False
    }

# Configurar logging
logger = SistemaLogging.obtener_logger('escuela', config.get('log_file', 'escuela_detallado.log'))

# Crear instancia de estado persistente
try:
    estado_archivo = config.get('estado_file', 'estado_escuela.json')
    estado = EstadoPersistenteBase(estado_archivo, 'escuela')
except Exception as e:
    logger.error(f"❌ Error creando estado persistente: {e}")
    # Estado de emergencia
    estado = None

# Instancia global del gestor SSH
try:
    gestor_ssh = GestorSSHCompartido()
except Exception as e:
    logger.error(f"❌ Error creando gestor SSH: {e}")
    gestor_ssh = None

# Instancia de utilidades
util = UtilidadesCompartidas()

# =============================================================================
# CONSTANTES Y CONFIGURACIÓN
# =============================================================================

# Configuración de la aplicación
APP_TITLE = "🏫 Sistema de Gestión Escolar"
APP_ICON = "🏫"
PAGE_SIZE = config.get('page_size', 50)
CACHE_TTL = config.get('cache_ttl', 300)

# Estados de los estudiantes
ESTADOS_ESTUDIANTE = ['Activo', 'Inactivo', 'Egresado', 'Baja Temporal', 'Baja Definitiva']
NIVELES_ESTUDIO = ['Licenciatura', 'Maestría', 'Doctorado', 'Especialidad']
TURNOS = ['Matutino', 'Vespertino', 'Nocturno', 'Mixto']

# =============================================================================
# CLASE PRINCIPAL DEL SISTEMA - CORREGIDA PARA STREAMLIT CLOUD
# =============================================================================

class SistemaGestionEscolar:
    """Clase principal del sistema de gestión escolar"""
    
    def __init__(self):
        self.config = config
        self.logger = logger
        self.estado = estado
        self.gestor_ssh = gestor_ssh
        self.util = util
        
        # Configuración de rutas
        self.rutas = config.get('remote_paths', {})
        self.ssh_config = config.get('ssh', {})
        
        # Estado interno
        self.conexion_local = None
        self.db_local_path = None
        self.cache_data = {}
        self.cache_timestamps = {}
        
        # Inicializar
        self._inicializar_sistema()
    
    def _inicializar_sistema(self):
        """Inicializar el sistema - CORREGIDO PARA STREAMLIT CLOUD"""
        self.logger.info("🚀 Inicializando Sistema de Gestión Escolar")
        
        # Verificar si ya está inicializado
        if not self.estado.esta_inicializada():
            self._inicializar_base_datos()
        else:
            self.logger.info(f"✅ Sistema ya inicializado el {self.estado.obtener_fecha_inicializacion()}")
        
        # Sincronizar si está configurado y hay SSH
        if self.config.get('sync_on_start', True) and self.ssh_config.get('enabled', False):
            self.sincronizar_con_servidor()
        elif self.ssh_config.get('enabled', False):
            self.logger.info("🔄 Sincronización al inicio deshabilitada")
        else:
            self.logger.info("🔌 SSH deshabilitado, omitiendo sincronización")
    
    def _inicializar_base_datos(self):
        """Inicializar la base de datos local - CORREGIDO PARA STREAMLIT CLOUD"""
        try:
            self.logger.info("🔄 Inicializando base de datos local...")
            
            # Streamlit Cloud: usar directorio temporal
            import tempfile
            temp_dir = tempfile.gettempdir()
            
            # Usar directorio temporal con nombre único
            timestamp = self.util.generar_timestamp()
            self.db_local_path = os.path.join(temp_dir, f"escuela_db_{timestamp}.db")
            
            # Eliminar si existe (por precaución)
            if os.path.exists(self.db_local_path):
                try:
                    os.remove(self.db_local_path)
                    self.logger.debug(f"Archivo existente eliminado: {self.db_local_path}")
                except Exception as e:
                    self.logger.warning(f"⚠️ No se pudo eliminar archivo existente: {e}")
            
            # Crear conexión
            self.conexion_local = sqlite3.connect(self.db_local_path, check_same_thread=False)
            self.conexion_local.row_factory = sqlite3.Row
            
            # Crear estructura de tablas
            self._crear_estructura_bd()
            
            # Marcar como inicializada
            self.estado.marcar_db_inicializada()
            self.logger.info(f"✅ Base de datos inicializada exitosamente en: {self.db_local_path}")
            
        except Exception as e:
            self.logger.error(f"❌ Error inicializando base de datos: {e}")
            
            # FALLBACK: base de datos en memoria
            try:
                self.logger.info("🔄 Intentando base de datos en memoria como fallback...")
                self.conexion_local = sqlite3.connect(":memory:", check_same_thread=False)
                self.conexion_local.row_factory = sqlite3.Row
                self._crear_estructura_bd()
                self.db_local_path = ":memory:"
                self.estado.marcar_db_inicializada()
                self.logger.info("✅ Base de datos en memoria creada como fallback")
            except Exception as e2:
                self.logger.error(f"❌ Error crítico: No se pudo crear BD: {e2}")
                st.error(f"Error crítico al inicializar la base de datos: {str(e2)}")
                raise
    
    def _crear_estructura_bd(self):
        """Crear estructura completa de la base de datos"""
        cursor = self.conexion_local.cursor()
        
        # Tabla de estudiantes
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
                email TEXT,
                direccion TEXT,
                ciudad TEXT,
                estado TEXT,
                codigo_postal TEXT,
                nivel_estudio TEXT,
                carrera TEXT,
                semestre INTEGER,
                turno TEXT,
                fecha_ingreso TEXT,
                fecha_egreso TEXT,
                estado_estudiante TEXT DEFAULT 'Activo',
                promedio REAL,
                creditos_aprobados INTEGER,
                creditos_totales INTEGER,
                foto_path TEXT,
                documentos_path TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de inscritos (matriculados por ciclo)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inscritos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estudiante_id INTEGER NOT NULL,
                ciclo_escolar TEXT NOT NULL,
                semestre INTEGER,
                fecha_inscripcion TEXT DEFAULT CURRENT_TIMESTAMP,
                estatus TEXT DEFAULT 'Inscrito',
                promedio_ciclo REAL,
                creditos_inscritos INTEGER,
                observaciones TEXT,
                FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id),
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
                numero_cedula TEXT,
                institucion_titulacion TEXT,
                empleo_actual TEXT,
                empresa_actual TEXT,
                salario_aproximado REAL,
                fecha_registro TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (estudiante_id) REFERENCES estudiantes (id)
            )
        ''')
        
        # Tabla de contratados (egresados con empleo)
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
                FOREIGN KEY (egresado_id) REFERENCES egresados (id)
            )
        ''')
        
        # Tabla de usuarios del sistema
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
        
        # Tabla de auditoría
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                accion TEXT NOT NULL,
                tabla_afectada TEXT,
                registro_id INTEGER,
                detalles TEXT,
                fecha_hora TEXT DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT
            )
        ''')
        
        # Tabla de configuraciones del sistema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuraciones (
                clave TEXT PRIMARY KEY,
                valor TEXT,
                descripcion TEXT,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insertar usuario administrador por defecto si no existe
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO usuarios (username, password_hash, nombre_completo, email, rol) VALUES (?, ?, ?, ?, ?)",
                ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'Administrador del Sistema', 'admin@escuela.edu.mx', 'admin')
            )
        
        self.conexion_local.commit()
        self.logger.info("✅ Estructura de base de datos creada")
    
    # =============================================================================
    # OPERACIONES DE SINCRONIZACIÓN CON SERVIDOR - CORREGIDAS
    # =============================================================================
    
    def sincronizar_con_servidor(self, forzar: bool = False):
        """Sincronizar datos con el servidor remoto - CORREGIDO"""
        try:
            if not self.ssh_config.get('enabled', True):
                self.logger.warning("SSH deshabilitado, omitiendo sincronización")
                return False
            
            self.logger.info("🔄 Sincronizando con servidor remoto...")
            
            # Conectar al servidor
            if not self.gestor_ssh or not self.gestor_ssh.conectar():
                self.logger.error("❌ No se pudo conectar al servidor SSH")
                return False
            
            sftp = self.gestor_ssh.obtener_sftp()
            if not sftp:
                self.logger.error("❌ No se pudo obtener cliente SFTP")
                return False
            
            # Descargar base de datos principal
            db_remota = self.rutas.get('escuela_db')
            if db_remota and self.db_local_path and self.db_local_path != ":memory:":
                try:
                    self._descargar_base_datos(sftp, db_remota, self.db_local_path)
                except Exception as e:
                    self.logger.error(f"❌ Error descargando BD principal: {e}")
                    # Continuar con otras operaciones
            
            # Descargar base de datos de inscritos si está configurada
            db_inscritos_remota = self.rutas.get('inscritos_db')
            if db_inscritos_remota:
                try:
                    temp_inscritos_path = self.util.crear_archivo_temporal(".db")
                    self._descargar_base_datos(sftp, db_inscritos_remota, temp_inscritos_path)
                    # Aquí podrías procesar o fusionar esta BD
                except Exception as e:
                    self.logger.warning(f"⚠️ Error descargando BD de inscritos: {e}")
            
            # Sincronizar archivos de uploads
            self._sincronizar_uploads(sftp)
            
            # Actualizar estado
            self.estado.marcar_sincronizacion()
            self.estado.set_ssh_conectado(True)
            
            # Limpiar cache
            self.cache_data.clear()
            self.cache_timestamps.clear()
            
            self.logger.info("✅ Sincronización completada exitosamente")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error en sincronización: {e}")
            self.estado.set_ssh_conectado(False, str(e))
            return False
    
    def _descargar_base_datos(self, sftp, ruta_remota: str, ruta_local: str):
        """Descargar base de datos desde servidor remoto"""
        try:
            self.logger.info(f"📥 Descargando {ruta_remota}...")
            
            # Verificar si existe localmente
            if os.path.exists(ruta_local):
                # Crear backup
                backup_path = f"{ruta_local}.backup_{self.util.generar_timestamp()}"
                try:
                    import shutil
                    shutil.copy2(ruta_local, backup_path)
                    self.logger.debug(f"Backup creado: {backup_path}")
                except Exception as e:
                    self.logger.warning(f"⚠️ No se pudo crear backup: {e}")
            
            # Descargar archivo
            sftp.get(ruta_remota, ruta_local)
            
            # Verificar que se descargó
            if os.path.exists(ruta_local):
                file_size = os.path.getsize(ruta_local)
                self.logger.info(f"✅ Base de datos descargada: {ruta_local} ({file_size} bytes)")
                
                # Re-conectar a la nueva BD
                if ruta_local == self.db_local_path:
                    self.conexion_local.close()
                    self.conexion_local = sqlite3.connect(self.db_local_path, check_same_thread=False)
                    self.conexion_local.row_factory = sqlite3.Row
                    self.logger.info("✅ Reconectado a base de datos descargada")
            else:
                self.logger.error(f"❌ Archivo descargado no encontrado: {ruta_local}")
            
        except FileNotFoundError:
            self.logger.warning(f"⚠️ Archivo remoto no encontrado: {ruta_remota}")
        except Exception as e:
            self.logger.error(f"❌ Error descargando base de datos: {e}")
            raise
    
    def _sincronizar_uploads(self, sftp):
        """Sincronizar archivos de uploads"""
        try:
            # Crear directorios locales si no existen
            directorios_uploads = [
                'uploads/inscritos',
                'uploads/estudiantes',
                'uploads/egresados',
                'uploads/contratados'
            ]
            
            for dir_path in directorios_uploads:
                self.util.crear_directorio_si_no_existe(dir_path)
            
            self.logger.info("✅ Directorios de uploads preparados")
            
            # Opcional: descargar archivos remotos si existen
            uploads_base = self.rutas.get('uploads_base')
            if uploads_base:
                try:
                    self.logger.info(f"📥 Descargando archivos de uploads desde {uploads_base}...")
                    # Aquí iría la lógica para sincronizar archivos
                except Exception as e:
                    self.logger.warning(f"⚠️ Error sincronizando uploads: {e}")
            
        except Exception as e:
            self.logger.error(f"❌ Error en sincronización de uploads: {e}")
    
    def subir_cambios_al_servidor(self):
        """Subir cambios locales al servidor remoto"""
        try:
            self.logger.info("🔼 Subiendo cambios al servidor...")
            
            if not self.ssh_config.get('enabled', True):
                self.logger.error("❌ SSH deshabilitado, no se pueden subir cambios")
                return False
            
            if not self.gestor_ssh or not self.gestor_ssh.conectar():
                self.logger.error("❌ No se pudo conectar al servidor SSH")
                return False
            
            sftp = self.gestor_ssh.obtener_sftp()
            if not sftp:
                self.logger.error("❌ No se pudo obtener cliente SFTP")
                return False
            
            # Subir base de datos principal
            db_remota = self.rutas.get('escuela_db')
            if db_remota and self.db_local_path and os.path.exists(self.db_local_path):
                sftp.put(self.db_local_path, db_remota)
                self.logger.info(f"✅ Base de datos subida: {db_remota}")
            
            self.logger.info("✅ Cambios subidos exitosamente")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error subiendo cambios: {e}")
            return False
    
    # =============================================================================
    # OPERACIONES DE BACKUP - CORREGIDAS
    # =============================================================================
    
    def crear_backup(self):
        """Crear backup de la base de datos - CORREGIDO"""
        try:
            if not self.config.get('backup', {}).get('enabled', True):
                self.logger.info("Backup deshabilitado en configuración")
                return True
            
            # Streamlit Cloud: usar directorio temporal
            import tempfile
            temp_dir = tempfile.gettempdir()
            
            backup_dir = os.path.join(temp_dir, self.config.get('backup_dir', 'backups_escuela'))
            self.util.crear_directorio_si_no_existe(backup_dir)
            
            # Verificar espacio en disco
            espacio_ok, espacio_mb = self.util.verificar_espacio_disco(
                backup_dir,
                self.config.get('backup', {}).get('min_disk_space_mb', 100)
            )
            
            if not espacio_ok:
                self.logger.warning(f"⚠️ Espacio insuficiente para backup: {espacio_mb:.2f} MB disponibles")
                return False
            
            timestamp = self.util.generar_timestamp()
            backup_file = os.path.join(backup_dir, f"escuela_backup_{timestamp}.db")
            
            # Crear copia de la base de datos
            import shutil
            shutil.copy2(self.db_local_path, backup_file)
            
            # Comprimir si es grande
            if os.path.getsize(backup_file) > 10 * 1024 * 1024:  # > 10MB
                try:
                    import gzip
                    with open(backup_file, 'rb') as f_in:
                        with gzip.open(f"{backup_file}.gz", 'wb') as f_out:
                            f_out.writelines(f_in)
                    os.remove(backup_file)
                    backup_file = f"{backup_file}.gz"
                    self.logger.info("✅ Backup comprimido")
                except Exception as e:
                    self.logger.warning(f"⚠️ No se pudo comprimir backup: {e}")
            
            # Limpiar backups antiguos
            self._limpiar_backups_antiguos(backup_dir)
            
            self.estado.registrar_backup()
            self.logger.info(f"✅ Backup creado: {backup_file}")
            
            # Opcional: subir backup al servidor
            if self.ssh_config.get('enabled', False):
                try:
                    self._subir_backup_al_servidor(backup_file)
                except Exception as e:
                    self.logger.warning(f"⚠️ No se pudo subir backup al servidor: {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error creando backup: {e}")
            return False
    
    def _subir_backup_al_servidor(self, backup_file: str):
        """Subir backup al servidor remoto"""
        if not self.gestor_ssh or not self.gestor_ssh.conectar():
            return False
        
        sftp = self.gestor_ssh.obtener_sftp()
        if not sftp:
            return False
        
        try:
            # Crear directorio de backups remoto si no existe
            remote_backup_dir = self.rutas.get('uploads_base', '') + '/backups'
            if remote_backup_dir:
                try:
                    sftp.mkdir(remote_backup_dir)
                except:
                    pass  # El directorio ya existe
            
            # Subir backup
            remote_path = os.path.join(remote_backup_dir, os.path.basename(backup_file))
            sftp.put(backup_file, remote_path)
            self.logger.info(f"✅ Backup subido al servidor: {remote_path}")
            return True
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error subiendo backup: {e}")
            return False
    
    def _limpiar_backups_antiguos(self, backup_dir: str):
        """Limpiar backups antiguos manteniendo solo los más recientes"""
        try:
            max_backups = self.config.get('backup', {}).get('max_backups', 10)
            
            if not os.path.exists(backup_dir):
                return
            
            backups = []
            for file in os.listdir(backup_dir):
                if file.startswith('escuela_backup_'):
                    file_path = os.path.join(backup_dir, file)
                    if os.path.isfile(file_path):
                        backups.append((file_path, os.path.getmtime(file_path)))
            
            if len(backups) <= max_backups:
                return
            
            # Ordenar por fecha de modificación (más antiguos primero)
            backups.sort(key=lambda x: x[1])
            
            # Eliminar los más antiguos si excedemos el máximo
            while len(backups) > max_backups:
                old_backup = backups.pop(0)
                try:
                    os.remove(old_backup[0])
                    self.logger.debug(f"Backup antiguo eliminado: {old_backup[0]}")
                except Exception as e:
                    self.logger.warning(f"⚠️ No se pudo eliminar backup antiguo: {e}")
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error limpiando backups antiguos: {e}")
    
    # =============================================================================
    # OPERACIONES CRUD PARA ESTUDIANTES
    # =============================================================================
    
    @st.cache_data(ttl=CACHE_TTL)
    def obtener_estudiantes(_self, filtro_estado: str = None, busqueda: str = None, limite: int = PAGE_SIZE):
        """Obtener lista de estudiantes con filtros"""
        try:
            query = "SELECT * FROM estudiantes WHERE 1=1"
            params = []
            
            if filtro_estado and filtro_estado != 'Todos':
                query += " AND estado_estudiante = ?"
                params.append(filtro_estado)
            
            if busqueda:
                query += " AND (matricula LIKE ? OR nombre LIKE ? OR apellido_paterno LIKE ? OR email LIKE ?)"
                search_term = f"%{busqueda}%"
                params.extend([search_term] * 4)
            
            query += " ORDER BY fecha_ingreso DESC LIMIT ?"
            params.append(limite)
            
            cursor = _self.conexion_local.cursor()
            cursor.execute(query, params)
            estudiantes = cursor.fetchall()
            
            return estudiantes
            
        except Exception as e:
            _self.logger.error(f"❌ Error obteniendo estudiantes: {e}")
            return []
    
    def obtener_estudiante_por_id(self, estudiante_id: int):
        """Obtener estudiante por ID"""
        try:
            cursor = self.conexion_local.cursor()
            cursor.execute("SELECT * FROM estudiantes WHERE id = ?", (estudiante_id,))
            return cursor.fetchone()
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo estudiante {estudiante_id}: {e}")
            return None
    
    def buscar_estudiante(self, criterio: str, valor: str):
        """Buscar estudiante por cualquier criterio"""
        try:
            criterios_validos = ['matricula', 'nombre', 'curp', 'email']
            if criterio not in criterios_validos:
                return None
            
            cursor = self.conexion_local.cursor()
            query = f"SELECT * FROM estudiantes WHERE {criterio} LIKE ?"
            cursor.execute(query, (f"%{valor}%",))
            return cursor.fetchall()
            
        except Exception as e:
            self.logger.error(f"❌ Error buscando estudiante: {e}")
            return []
    
    def agregar_estudiante(self, datos_estudiante: dict):
        """Agregar nuevo estudiante"""
        try:
            cursor = self.conexion_local.cursor()
            
            # Preparar campos y valores
            campos = []
            placeholders = []
            valores = []
            
            for campo, valor in datos_estudiante.items():
                if valor is not None and valor != '':
                    campos.append(campo)
                    placeholders.append('?')
                    valores.append(valor)
            
            # Añadir fechas de creación y actualización
            campos.append('fecha_creacion')
            campos.append('fecha_actualizacion')
            placeholders.append('CURRENT_TIMESTAMP')
            placeholders.append('CURRENT_TIMESTAMP')
            
            query = f"INSERT INTO estudiantes ({', '.join(campos)}) VALUES ({', '.join(placeholders)})"
            
            cursor.execute(query, valores)
            self.conexion_local.commit()
            
            estudiante_id = cursor.lastrowid
            self.logger.info(f"✅ Estudiante agregado: ID {estudiante_id}")
            
            # Registrar en auditoría
            self._registrar_auditoria('INSERT', 'estudiantes', estudiante_id, 
                                     f"Estudiante creado: {datos_estudiante.get('matricula', 'N/A')}")
            
            return estudiante_id
            
        except sqlite3.IntegrityError as e:
            self.logger.error(f"❌ Error de integridad al agregar estudiante: {e}")
            if "matricula" in str(e):
                raise ValueError("La matrícula ya existe")
            elif "curp" in str(e):
                raise ValueError("El CURP ya existe")
            else:
                raise ValueError("Error de duplicación de datos")
        except Exception as e:
            self.logger.error(f"❌ Error agregando estudiante: {e}")
            raise
    
    def actualizar_estudiante(self, estudiante_id: int, datos_actualizados: dict):
        """Actualizar estudiante existente"""
        try:
            # Obtener estudiante actual
            estudiante_actual = self.obtener_estudiante_por_id(estudiante_id)
            if not estudiante_actual:
                raise ValueError(f"Estudiante {estudiante_id} no encontrado")
            
            # Preparar SET clauses
            set_clauses = []
            valores = []
            
            for campo, valor in datos_actualizados.items():
                if campo not in ['id', 'fecha_creacion']:  # Campos que no se actualizan
                    if valor != estudiante_actual[campo]:  # Solo actualizar si cambió
                        set_clauses.append(f"{campo} = ?")
                        valores.append(valor)
            
            if not set_clauses:
                self.logger.warning(f"⚠️ No hay cambios para actualizar en estudiante {estudiante_id}")
                return True
            
            # Añadir fecha de actualización
            set_clauses.append("fecha_actualizacion = CURRENT_TIMESTAMP")
            
            # Construir y ejecutar query
            valores.append(estudiante_id)
            query = f"UPDATE estudiantes SET {', '.join(set_clauses)} WHERE id = ?"
            
            cursor = self.conexion_local.cursor()
            cursor.execute(query, valores)
            self.conexion_local.commit()
            
            self.logger.info(f"✅ Estudiante actualizado: ID {estudiante_id}")
            
            # Registrar en auditoría
            cambios = ', '.join([f"{k}: {v}" for k, v in datos_actualizados.items() 
                               if k in datos_actualizados and estudiante_actual[k] != v])
            self._registrar_auditoria('UPDATE', 'estudiantes', estudiante_id, 
                                     f"Estudiante actualizado: {cambios}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error actualizando estudiante {estudiante_id}: {e}")
            raise
    
    def eliminar_estudiante(self, estudiante_id: int):
        """Eliminar estudiante (baja lógica)"""
        try:
            cursor = self.conexion_local.cursor()
            
            # Verificar si tiene registros relacionados
            cursor.execute("SELECT COUNT(*) FROM inscritos WHERE estudiante_id = ?", (estudiante_id,))
            if cursor.fetchone()[0] > 0:
                raise ValueError("No se puede eliminar estudiante con inscripciones activas")
            
            cursor.execute("SELECT COUNT(*) FROM egresados WHERE estudiante_id = ?", (estudiante_id,))
            if cursor.fetchone()[0] > 0:
                raise ValueError("No se puede eliminar estudiante egresado")
            
            # Baja lógica (cambio de estado)
            cursor.execute(
                "UPDATE estudiantes SET estado_estudiante = 'Baja Definitiva', fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ?",
                (estudiante_id,)
            )
            self.conexion_local.commit()
            
            self.logger.info(f"✅ Estudiante dado de baja: ID {estudiante_id}")
            
            # Registrar en auditoría
            self._registrar_auditoria('UPDATE', 'estudiantes', estudiante_id, 
                                     "Estudiante dado de baja (Baja Definitiva)")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error eliminando estudiante {estudiante_id}: {e}")
            raise
    
    def cambiar_estado_estudiante(self, estudiante_id: int, nuevo_estado: str):
        """Cambiar estado de estudiante"""
        try:
            if nuevo_estado not in ESTADOS_ESTUDIANTE:
                raise ValueError(f"Estado inválido. Debe ser: {', '.join(ESTADOS_ESTUDIANTE)}")
            
            cursor = self.conexion_local.cursor()
            cursor.execute(
                "UPDATE estudiantes SET estado_estudiante = ?, fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = ?",
                (nuevo_estado, estudiante_id)
            )
            
            if cursor.rowcount == 0:
                raise ValueError(f"Estudiante {estudiante_id} no encontrado")
            
            self.conexion_local.commit()
            
            self.logger.info(f"✅ Estado cambiado a '{nuevo_estado}' para estudiante {estudiante_id}")
            
            # Registrar en auditoría
            self._registrar_auditoria('UPDATE', 'estudiantes', estudiante_id, 
                                     f"Estado cambiado a: {nuevo_estado}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error cambiando estado del estudiante {estudiante_id}: {e}")
            raise
    
    # =============================================================================
    # OPERACIONES PARA INSCRITOS
    # =============================================================================
    
    def obtener_inscripciones(self, estudiante_id: int = None, ciclo_escolar: str = None):
        """Obtener inscripciones"""
        try:
            query = """
                SELECT i.*, e.matricula, e.nombre, e.apellido_paterno, e.apellido_materno
                FROM inscritos i
                JOIN estudiantes e ON i.estudiante_id = e.id
                WHERE 1=1
            """
            params = []
            
            if estudiante_id:
                query += " AND i.estudiante_id = ?"
                params.append(estudiante_id)
            
            if ciclo_escolar:
                query += " AND i.ciclo_escolar = ?"
                params.append(ciclo_escolar)
            
            query += " ORDER BY i.fecha_inscripcion DESC"
            
            cursor = self.conexion_local.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo inscripciones: {e}")
            return []
    
    def inscribir_estudiante(self, estudiante_id: int, ciclo_escolar: str, 
                            semestre: int = None, creditos_inscritos: int = None):
        """Inscribir estudiante en un ciclo escolar"""
        try:
            # Verificar que el estudiante existe y está activo
            cursor = self.conexion_local.cursor()
            cursor.execute(
                "SELECT estado_estudiante FROM estudiantes WHERE id = ?",
                (estudiante_id,)
            )
            resultado = cursor.fetchone()
            
            if not resultado:
                raise ValueError(f"Estudiante {estudiante_id} no encontrado")
            
            if resultado[0] != 'Activo':
                raise ValueError(f"Estudiante no está activo (estado: {resultado[0]})")
            
            # Verificar que no esté ya inscrito en el mismo ciclo
            cursor.execute(
                "SELECT COUNT(*) FROM inscritos WHERE estudiante_id = ? AND ciclo_escolar = ?",
                (estudiante_id, ciclo_escolar)
            )
            if cursor.fetchone()[0] > 0:
                raise ValueError(f"Estudiante ya inscrito en el ciclo {ciclo_escolar}")
            
            # Insertar inscripción
            cursor.execute("""
                INSERT INTO inscritos (estudiante_id, ciclo_escolar, semestre, creditos_inscritos, fecha_inscripcion)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (estudiante_id, ciclo_escolar, semestre, creditos_inscritos))
            
            self.conexion_local.commit()
            
            inscripcion_id = cursor.lastrowid
            self.logger.info(f"✅ Estudiante {estudiante_id} inscrito en ciclo {ciclo_escolar}")
            
            # Registrar en auditoría
            self._registrar_auditoria('INSERT', 'inscritos', inscripcion_id,
                                     f"Estudiante {estudiante_id} inscrito en {ciclo_escolar}")
            
            return inscripcion_id
            
        except Exception as e:
            self.logger.error(f"❌ Error inscribiendo estudiante {estudiante_id}: {e}")
            raise
    
    def actualizar_promedio_inscripcion(self, inscripcion_id: int, promedio_ciclo: float):
        """Actualizar promedio de una inscripción"""
        try:
            cursor = self.conexion_local.cursor()
            cursor.execute(
                "UPDATE inscritos SET promedio_ciclo = ? WHERE id = ?",
                (promedio_ciclo, inscripcion_id)
            )
            
            if cursor.rowcount == 0:
                raise ValueError(f"Inscripción {inscripcion_id} no encontrada")
            
            self.conexion_local.commit()
            
            self.logger.info(f"✅ Promedio actualizado para inscripción {inscripcion_id}: {promedio_ciclo}")
            
            # Registrar en auditoría
            self._registrar_auditoria('UPDATE', 'inscritos', inscripcion_id,
                                     f"Promedio actualizado a {promedio_ciclo}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error actualizando promedio para inscripción {inscripcion_id}: {e}")
            raise
    
    # =============================================================================
    # OPERACIONES PARA EGRESADOS
    # =============================================================================
    
    def registrar_egresado(self, estudiante_id: int, fecha_egreso: str,
                          titulo_obtenido: str = None, promedio_final: float = None):
        """Registrar estudiante como egresado"""
        try:
            # Verificar que el estudiante existe
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            if not estudiante:
                raise ValueError(f"Estudiante {estudiante_id} no encontrado")
            
            # Verificar que no esté ya registrado como egresado
            cursor = self.conexion_local.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM egresados WHERE estudiante_id = ?",
                (estudiante_id,)
            )
            if cursor.fetchone()[0] > 0:
                raise ValueError(f"Estudiante {estudiante_id} ya está registrado como egresado")
            
            # Insertar registro de egresado
            cursor.execute("""
                INSERT INTO egresados (estudiante_id, fecha_egreso, titulo_obtenido, promedio_final, fecha_registro)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (estudiante_id, fecha_egreso, titulo_obtenido, promedio_final))
            
            # Actualizar estado del estudiante
            cursor.execute(
                "UPDATE estudiantes SET estado_estudiante = 'Egresado', fecha_egreso = ? WHERE id = ?",
                (fecha_egreso, estudiante_id)
            )
            
            self.conexion_local.commit()
            
            egresado_id = cursor.lastrowid
            self.logger.info(f"✅ Egresado registrado: ID {egresado_id} (Estudiante: {estudiante_id})")
            
            # Registrar en auditoría
            self._registrar_auditoria('INSERT', 'egresados', egresado_id,
                                     f"Estudiante {estudiante_id} registrado como egresado")
            
            return egresado_id
            
        except Exception as e:
            self.logger.error(f"❌ Error registrando egresado {estudiante_id}: {e}")
            raise
    
    def obtener_egresados(self, filtro_titulo: str = None, filtro_fecha_desde: str = None):
        """Obtener lista de egresados"""
        try:
            query = """
                SELECT e.*, est.matricula, est.nombre, est.apellido_paterno, est.apellido_materno,
                       est.carrera, est.nivel_estudio
                FROM egresados e
                JOIN estudiantes est ON e.estudiante_id = est.id
                WHERE 1=1
            """
            params = []
            
            if filtro_titulo:
                query += " AND e.titulo_obtenido LIKE ?"
                params.append(f"%{filtro_titulo}%")
            
            if filtro_fecha_desde:
                query += " AND e.fecha_egreso >= ?"
                params.append(filtro_fecha_desde)
            
            query += " ORDER BY e.fecha_egreso DESC"
            
            cursor = self.conexion_local.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo egresados: {e}")
            return []
    
    # =============================================================================
    # OPERACIONES PARA CONTRATADOS
    # =============================================================================
    
    def registrar_contratacion(self, egresado_id: int, empresa: str, 
                              puesto: str = None, fecha_contratacion: str = None,
                              salario_inicial: float = None, tipo_contrato: str = None):
        """Registrar contratación de egresado"""
        try:
            # Verificar que el egresado existe
            cursor = self.conexion_local.cursor()
            cursor.execute(
                "SELECT estudiante_id FROM egresados WHERE id = ?",
                (egresado_id,)
            )
            resultado = cursor.fetchone()
            
            if not resultado:
                raise ValueError(f"Egresado {egresado_id} no encontrado")
            
            # Insertar registro de contratación
            cursor.execute("""
                INSERT INTO contratados (egresado_id, empresa, puesto, fecha_contratacion, 
                                       salario_inicial, tipo_contrato, fecha_registro)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (egresado_id, empresa, puesto, fecha_contratacion, salario_inicial, tipo_contrato))
            
            self.conexion_local.commit()
            
            contratado_id = cursor.lastrowid
            self.logger.info(f"✅ Contratación registrada: ID {contratado_id} (Egresado: {egresado_id})")
            
            # Registrar en auditoría
            self._registrar_auditoria('INSERT', 'contratados', contratado_id,
                                     f"Egresado {egresado_id} contratado por {empresa}")
            
            return contratado_id
            
        except Exception as e:
            self.logger.error(f"❌ Error registrando contratación para egresado {egresado_id}: {e}")
            raise
    
    def obtener_contratados(self, filtro_empresa: str = None, filtro_puesto: str = None):
        """Obtener lista de egresados contratados"""
        try:
            query = """
                SELECT c.*, e.estudiante_id, e.titulo_obtenido, e.promedio_final,
                       est.matricula, est.nombre, est.apellido_paterno, est.apellido_materno,
                       est.carrera
                FROM contratados c
                JOIN egresados e ON c.egresado_id = e.id
                JOIN estudiantes est ON e.estudiante_id = est.id
                WHERE 1=1
            """
            params = []
            
            if filtro_empresa:
                query += " AND c.empresa LIKE ?"
                params.append(f"%{filtro_empresa}%")
            
            if filtro_puesto:
                query += " AND c.puesto LIKE ?"
                params.append(f"%{filtro_puesto}%")
            
            query += " ORDER BY c.fecha_contratacion DESC"
            
            cursor = self.conexion_local.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo contratados: {e}")
            return []
    
    # =============================================================================
    # ESTADÍSTICAS E INFORMES
    # =============================================================================
    
    def obtener_estadisticas_generales(self):
        """Obtener estadísticas generales del sistema"""
        try:
            cursor = self.conexion_local.cursor()
            estadisticas = {}
            
            # Total de estudiantes por estado
            cursor.execute("""
                SELECT estado_estudiante, COUNT(*) as total
                FROM estudiantes
                GROUP BY estado_estudiante
            """)
            resultados = cursor.fetchall()
            if resultados:
                estadisticas['estudiantes_por_estado'] = dict(resultados)
            else:
                estadisticas['estudiantes_por_estado'] = {}
            
            # Total de estudiantes
            estadisticas['total_estudiantes'] = sum(estadisticas['estudiantes_por_estado'].values())
            
            # Estudiantes activos
            estadisticas['estudiantes_activos'] = estadisticas['estudiantes_por_estado'].get('Activo', 0)
            
            # Egresados
            cursor.execute("SELECT COUNT(*) FROM egresados")
            estadisticas['total_egresados'] = cursor.fetchone()[0] or 0
            
            # Contratados
            cursor.execute("SELECT COUNT(DISTINCT egresado_id) FROM contratados")
            estadisticas['egresados_contratados'] = cursor.fetchone()[0] or 0
            
            # Promedio general de estudiantes activos
            cursor.execute("SELECT AVG(promedio) FROM estudiantes WHERE estado_estudiante = 'Activo' AND promedio IS NOT NULL")
            resultado = cursor.fetchone()
            estadisticas['promedio_general'] = resultado[0] if resultado and resultado[0] else 0
            
            # Estudiantes por nivel de estudio
            cursor.execute("""
                SELECT nivel_estudio, COUNT(*) as total
                FROM estudiantes
                WHERE nivel_estudio IS NOT NULL
                GROUP BY nivel_estudio
            """)
            resultados = cursor.fetchall()
            if resultados:
                estadisticas['estudiantes_por_nivel'] = dict(resultados)
            else:
                estadisticas['estudiantes_por_nivel'] = {}
            
            # Estudiantes por carrera
            cursor.execute("""
                SELECT carrera, COUNT(*) as total
                FROM estudiantes
                WHERE carrera IS NOT NULL
                GROUP BY carrera
                ORDER BY total DESC
                LIMIT 10
            """)
            resultados = cursor.fetchall()
            if resultados:
                estadisticas['top_carreras'] = dict(resultados)
            else:
                estadisticas['top_carreras'] = {}
            
            # Inscripciones por ciclo escolar
            cursor.execute("""
                SELECT ciclo_escolar, COUNT(*) as total
                FROM inscritos
                GROUP BY ciclo_escolar
                ORDER BY ciclo_escolar DESC
                LIMIT 5
            """)
            resultados = cursor.fetchall()
            if resultados:
                estadisticas['inscripciones_por_ciclo'] = dict(resultados)
            else:
                estadisticas['inscripciones_por_ciclo'] = {}
            
            return estadisticas
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo estadísticas: {e}")
            # Devolver estadísticas vacías pero estructuradas
            return {
                'estudiantes_por_estado': {},
                'total_estudiantes': 0,
                'estudiantes_activos': 0,
                'total_egresados': 0,
                'egresados_contratados': 0,
                'promedio_general': 0,
                'estudiantes_por_nivel': {},
                'top_carreras': {},
                'inscripciones_por_ciclo': {}
            }
    
    def generar_informe_excel(self, tipo_informe: str = 'estudiantes'):
        """Generar informe en formato Excel"""
        try:
            import pandas as pd
            
            if tipo_informe == 'estudiantes':
                query = "SELECT * FROM estudiantes ORDER BY fecha_ingreso DESC"
                nombre_archivo = f"informe_estudiantes_{self.util.generar_timestamp()}.xlsx"
                
            elif tipo_informe == 'egresados':
                query = """
                    SELECT e.*, est.matricula, est.nombre, est.apellido_paterno, est.apellido_materno
                    FROM egresados e
                    JOIN estudiantes est ON e.estudiante_id = est.id
                    ORDER BY e.fecha_egreso DESC
                """
                nombre_archivo = f"informe_egresados_{self.util.generar_timestamp()}.xlsx"
                
            elif tipo_informe == 'contratados':
                query = """
                    SELECT c.*, est.matricula, est.nombre, est.carrera, e.titulo_obtenido
                    FROM contratados c
                    JOIN egresados e ON c.egresado_id = e.id
                    JOIN estudiantes est ON e.estudiante_id = est.id
                    ORDER BY c.fecha_contratacion DESC
                """
                nombre_archivo = f"informe_contratados_{self.util.generar_timestamp()}.xlsx"
                
            else:
                raise ValueError(f"Tipo de informe no válido: {tipo_informe}")
            
            # Ejecutar consulta y crear DataFrame
            df = pd.read_sql_query(query, self.conexion_local)
            
            # Si no hay datos, crear DataFrame vacío
            if df.empty:
                df = pd.DataFrame({'Mensaje': ['No hay datos para el informe seleccionado']})
            
            # Crear archivo Excel en memoria
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Datos', index=False)
            
            output.seek(0)
            
            self.logger.info(f"✅ Informe {tipo_informe} generado: {nombre_archivo}")
            return output, nombre_archivo
            
        except Exception as e:
            self.logger.error(f"❌ Error generando informe Excel: {e}")
            
            # Crear informe de error
            df = pd.DataFrame({'Error': [str(e)]})
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Error', index=False)
            output.seek(0)
            
            return output, f"error_informe_{self.util.generar_timestamp()}.xlsx"
    
    # =============================================================================
    # UTILIDADES Y MÉTODOS AUXILIARES
    # =============================================================================
    
    def _registrar_auditoria(self, accion: str, tabla: str, registro_id: int, detalles: str = None):
        """Registrar acción en auditoría"""
        try:
            cursor = self.conexion_local.cursor()
            
            # Obtener usuario actual si hay sesión
            usuario_id = None
            if hasattr(st, 'session_state') and hasattr(st.session_state, 'get'):
                usuario_id = st.session_state.get('usuario_id')
            
            cursor.execute("""
                INSERT INTO auditoria (usuario_id, accion, tabla_afectada, registro_id, detalles)
                VALUES (?, ?, ?, ?, ?)
            """, (usuario_id, accion, tabla, registro_id, detalles))
            
            self.conexion_local.commit()
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error registrando auditoría: {e}")
    
    def validar_datos_estudiante(self, datos: dict) -> list:
        """Validar datos de estudiante antes de insertar/actualizar"""
        errores = []
        
        # Validar matrícula
        if not datos.get('matricula'):
            errores.append("La matrícula es obligatoria")
        elif not self.util.validar_matricula(datos['matricula']):
            errores.append("Formato de matrícula inválido")
        
        # Validar nombre
        if not datos.get('nombre'):
            errores.append("El nombre es obligatorio")
        
        # Validar apellido paterno
        if not datos.get('apellido_paterno'):
            errores.append("El apellido paterno es obligatorio")
        
        # Validar email
        if datos.get('email') and not self.util.validar_email(datos['email']):
            errores.append("Formato de email inválido")
        
        # Validar CURP si se proporciona
        if datos.get('curp') and len(datos['curp']) != 18:
            errores.append("El CURP debe tener 18 caracteres")
        
        # Validar fecha de nacimiento
        if datos.get('fecha_nacimiento'):
            try:
                fecha_nac = datetime.strptime(datos['fecha_nacimiento'], '%Y-%m-%d')
                if fecha_nac > datetime.now():
                    errores.append("La fecha de nacimiento no puede ser futura")
            except:
                errores.append("Formato de fecha inválido (usar YYYY-MM-DD)")
        
        return errores
    
    def obtener_proximo_ciclo_escolar(self):
        """Obtener el próximo ciclo escolar basado en la fecha actual"""
        hoy = datetime.now()
        año_actual = hoy.year
        mes_actual = hoy.month
        
        # Si estamos después de junio, el próximo ciclo es del siguiente año
        if mes_actual > 6:
            return f"{año_actual}-{año_actual + 1}"
        else:
            return f"{año_actual - 1}-{año_actual}"
    
    def limpiar_cache(self):
        """Limpiar caché del sistema"""
        self.cache_data.clear()
        self.cache_timestamps.clear()
        self.logger.info("🗑️ Caché limpiado")
    
    def obtener_edad_estudiante(self, estudiante_id: int) -> int:
        """Obtener edad del estudiante"""
        estudiante = self.obtener_estudiante_por_id(estudiante_id)
        if estudiante and estudiante.get('fecha_nacimiento'):
            return self.util.calcular_edad(estudiante['fecha_nacimiento'])
        return None
    
    def formatear_salario(self, salario: float) -> str:
        """Formatear salario para mostrar"""
        return self.util.formatear_dinero(salario) if salario else "No especificado"
    
    # =============================================================================
    # MÉTODOS PARA LA INTERFAZ WEB
    # =============================================================================
    
    def mostrar_panel_control(self):
        """Mostrar panel de control principal"""
        st.title("📊 Panel de Control - Sistema de Gestión Escolar")
        
        # Estado del sistema
        col1, col2 = st.columns(2)
        with col1:
            if self.estado.esta_inicializada():
                st.success("✅ Sistema inicializado")
            else:
                st.error("❌ Sistema no inicializado")
        
        with col2:
            if self.ssh_config.get('enabled', False):
                if self.estado.estado.get('ssh_conectado'):
                    st.success("🔗 Conectado al servidor")
                else:
                    st.error("❌ Desconectado del servidor")
            else:
                st.info("🔌 SSH deshabilitado")
        
        # Estadísticas rápidas
        estadisticas = self.obtener_estadisticas_generales()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🏫 Total Estudiantes", estadisticas.get('total_estudiantes', 0))
        with col2:
            st.metric("✅ Estudiantes Activos", estadisticas.get('estudiantes_activos', 0))
        with col3:
            st.metric("🎓 Egresados", estadisticas.get('total_egresados', 0))
        with col4:
            st.metric("💼 Contratados", estadisticas.get('egresados_contratados', 0))
        
        # Gráfico de distribución por estado
        if estadisticas.get('estudiantes_por_estado'):
            st.subheader("📈 Distribución de Estudiantes por Estado")
            df_estados = pd.DataFrame(
                list(estadisticas['estudiantes_por_estado'].items()),
                columns=['Estado', 'Cantidad']
            )
            st.bar_chart(df_estados.set_index('Estado'))
        
        # Información del sistema
        with st.expander("ℹ️ Información del Sistema"):
            st.write(f"**Base de datos:** {self.db_local_path}")
            st.write(f"**Modo SSH:** {'Habilitado' if self.ssh_config.get('enabled', False) else 'Deshabilitado'}")
            
            if self.estado.estado.get('ultima_sincronizacion'):
                fecha_sync = datetime.fromisoformat(self.estado.estado['ultima_sincronizacion'])
                st.write(f"**Última sincronización:** {fecha_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            
            st.write(f"**Backups realizados:** {self.estado.estado.get('backups_realizados', 0)}")
    
    def mostrar_gestion_estudiantes(self):
        """Mostrar interfaz de gestión de estudiantes"""
        st.title("👨‍🎓 Gestión de Estudiantes")
        
        # Pestañas para diferentes funciones
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
            filtro_estado = st.selectbox(
                "Filtrar por estado:",
                ['Todos'] + ESTADOS_ESTUDIANTE
            )
        
        with col2:
            filtro_nivel = st.selectbox(
                "Filtrar por nivel:",
                ['Todos'] + NIVELES_ESTUDIO
            )
        
        with col3:
            busqueda = st.text_input("Buscar (matrícula/nombre):")
        
        # Obtener estudiantes
        estudiantes = self.obtener_estudiantes(
            filtro_estado if filtro_estado != 'Todos' else None,
            busqueda if busqueda else None,
            100  # Límite aumentado para la vista
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
            
            st.dataframe(df[columnas_existentes], use_container_width=True)
            
            # Opciones para cada estudiante
            st.subheader("Acciones")
            if estudiantes:
                estudiante_seleccionado = st.selectbox(
                    "Seleccionar estudiante:",
                    [f"{e['id']} - {e['matricula']} - {e['nombre']} {e['apellido_paterno']}" 
                     for e in estudiantes]
                )
                
                if estudiante_seleccionado:
                    estudiante_id = int(estudiante_seleccionado.split(' - ')[0])
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("📝 Editar", key=f"editar_{estudiante_id}"):
                            st.session_state['editar_estudiante'] = estudiante_id
                    
                    with col2:
                        nuevo_estado = st.selectbox(
                            "Cambiar estado:",
                            ESTADOS_ESTUDIANTE,
                            key=f"estado_{estudiante_id}"
                        )
                        if st.button("🔄 Actualizar", key=f"actualizar_estado_{estudiante_id}"):
                            try:
                                self.cambiar_estado_estudiante(estudiante_id, nuevo_estado)
                                st.success(f"✅ Estado cambiado a {nuevo_estado}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {e}")
                    
                    with col3:
                        if st.button("🗑️ Dar de baja", key=f"baja_{estudiante_id}"):
                            if st.checkbox(f"¿Confirmar baja del estudiante {estudiante_id}?"):
                                try:
                                    self.eliminar_estudiante(estudiante_id)
                                    st.success("✅ Estudiante dado de baja")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
        else:
            st.info("📭 No hay estudiantes que coincidan con los filtros")
            
            # Botón para crear primer estudiante
            if st.button("➕ Crear primer estudiante"):
                st.session_state['crear_estudiante'] = True
                st.rerun()
    
    def _mostrar_formulario_nuevo_estudiante(self):
        """Mostrar formulario para nuevo estudiante"""
        st.subheader("➕ Registrar Nuevo Estudiante")
        
        with st.form("form_nuevo_estudiante"):
            col1, col2 = st.columns(2)
            
            with col1:
                matricula = st.text_input("Matrícula *", max_chars=20)
                nombre = st.text_input("Nombre *", max_chars=100)
                apellido_paterno = st.text_input("Apellido Paterno *", max_chars=100)
                apellido_materno = st.text_input("Apellido Materno", max_chars=100)
                fecha_nacimiento = st.date_input("Fecha de Nacimiento")
                genero = st.selectbox("Género", ['M', 'F', 'Otro'])
                curp = st.text_input("CURP", max_chars=18)
                rfc = st.text_input("RFC", max_chars=13)
            
            with col2:
                telefono = st.text_input("Teléfono", max_chars=15)
                email = st.text_input("Email", max_chars=100)
                direccion = st.text_area("Dirección", max_chars=200)
                ciudad = st.text_input("Ciudad", max_chars=100)
                estado_res = st.text_input("Estado", max_chars=50)
                codigo_postal = st.text_input("Código Postal", max_chars=10)
                nivel_estudio = st.selectbox("Nivel de Estudio", NIVELES_ESTUDIO)
                carrera = st.text_input("Carrera", max_chars=100)
                semestre = st.number_input("Semestre", min_value=1, max_value=20, value=1)
                turno = st.selectbox("Turno", TURNOS)
                fecha_ingreso = st.date_input("Fecha de Ingreso", value=datetime.now())
            
            # Botón de enviar
            if st.form_submit_button("💾 Guardar Estudiante"):
                # Preparar datos
                datos_estudiante = {
                    'matricula': matricula,
                    'nombre': nombre,
                    'apellido_paterno': apellido_paterno,
                    'apellido_materno': apellido_materno,
                    'fecha_nacimiento': fecha_nacimiento.isoformat() if fecha_nacimiento else None,
                    'genero': genero,
                    'curp': curp if curp else None,
                    'rfc': rfc if rfc else None,
                    'telefono': telefono if telefono else None,
                    'email': email if email else None,
                    'direccion': direccion if direccion else None,
                    'ciudad': ciudad if ciudad else None,
                    'estado': estado_res if estado_res else None,
                    'codigo_postal': codigo_postal if codigo_postal else None,
                    'nivel_estudio': nivel_estudio,
                    'carrera': carrera if carrera else None,
                    'semestre': semestre,
                    'turno': turno,
                    'fecha_ingreso': fecha_ingreso.isoformat() if fecha_ingreso else None,
                    'estado_estudiante': 'Activo'
                }
                
                # Validar datos
                errores = self.validar_datos_estudiante(datos_estudiante)
                
                if errores:
                    for error in errores:
                        st.error(f"❌ {error}")
                else:
                    try:
                        estudiante_id = self.agregar_estudiante(datos_estudiante)
                        st.success(f"✅ Estudiante registrado exitosamente con ID: {estudiante_id}")
                        
                        # Preguntar si desea inscribirlo
                        if st.checkbox("📝 ¿Inscribir al estudiante en el ciclo actual?", value=True):
                            ciclo_actual = self.obtener_proximo_ciclo_escolar()
                            try:
                                self.inscribir_estudiante(estudiante_id, ciclo_actual, semestre)
                                st.success(f"✅ Estudiante inscrito en ciclo {ciclo_actual}")
                            except Exception as e:
                                st.warning(f"⚠️ No se pudo inscribir: {e}")
                        
                        # Limpiar formulario
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Error registrando estudiante: {e}")
    
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
            resultados = self.buscar_estudiante(criterio, valor)
            
            if resultados:
                st.success(f"✅ Encontrados {len(resultados)} estudiantes")
                
                df = pd.DataFrame(resultados)
                columnas_mostrar = ['id', 'matricula', 'nombre', 'apellido_paterno', 
                                  'apellido_materno', 'carrera', 'estado_estudiante']
                
                columnas_existentes = [col for col in columnas_mostrar if col in df.columns]
                st.dataframe(df[columnas_existentes], use_container_width=True)
            else:
                st.info("📭 No se encontraron estudiantes con esos criterios")
    
    def _mostrar_estadisticas_estudiantes(self):
        """Mostrar estadísticas de estudiantes"""
        estadisticas = self.obtener_estadisticas_generales()
        
        st.subheader("📊 Estadísticas de Estudiantes")
        
        # Distribución por nivel de estudio
        if estadisticas.get('estudiantes_por_nivel'):
            st.write("### 📚 Distribución por Nivel de Estudio")
            df_niveles = pd.DataFrame(
                list(estadisticas['estudiantes_por_nivel'].items()),
                columns=['Nivel', 'Cantidad']
            )
            st.bar_chart(df_niveles.set_index('Nivel'))
        
        # Top carreras
        if estadisticas.get('top_carreras'):
            st.write("### 🏆 Carreras con más estudiantes")
            df_carreras = pd.DataFrame(
                list(estadisticas['top_carreras'].items()),
                columns=['Carrera', 'Cantidad']
            )
            st.dataframe(df_carreras, use_container_width=True)
        
        # Exportar datos
        st.write("### 📤 Exportar Datos")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 Generar Informe Excel (Estudiantes)"):
                try:
                    output, nombre = self.generar_informe_excel('estudiantes')
                    st.download_button(
                        label="⬇️ Descargar Informe",
                        data=output,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.error(f"❌ Error generando informe: {e}")
        
        with col2:
            if st.button("📊 Generar Informe Excel (Egresados)"):
                try:
                    output, nombre = self.generar_informe_excel('egresados')
                    st.download_button(
                        label="⬇️ Descargar Informe",
                        data=output,
                        file_name=nombre,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.error(f"❌ Error generando informe: {e}")
    
    def mostrar_gestion_inscripciones(self):
        """Mostrar interfaz de gestión de inscripciones"""
        st.title("📝 Gestión de Inscripciones")
        
        # Obtener ciclo escolar actual
        ciclo_actual = self.obtener_proximo_ciclo_escolar()
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
        inscripciones = self.obtener_inscripciones(ciclo_escolar=ciclo_actual)
        
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
            st.dataframe(df, use_container_width=True)
            
            # Opciones para actualizar promedio
            st.subheader("Actualizar Promedios")
            if inscripciones:
                inscripcion_id = st.selectbox(
                    "Seleccionar inscripción:",
                    [f"{ins['id']} - {ins['matricula']} - {ins['nombre']}" for ins in inscripciones]
                )
                
                if inscripcion_id:
                    ins_id = int(inscripcion_id.split(' - ')[0])
                    nuevo_promedio = st.number_input(
                        "Nuevo promedio:", 
                        min_value=0.0, 
                        max_value=10.0, 
                        value=0.0,
                        step=0.1
                    )
                    
                    if st.button("💾 Actualizar Promedio"):
                        try:
                            self.actualizar_promedio_inscripcion(ins_id, nuevo_promedio)
                            st.success("✅ Promedio actualizado")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
        else:
            st.info(f"📭 No hay inscripciones para el ciclo {ciclo_actual}")
            
            # Botón para crear primera inscripción
            if st.button("➕ Crear primera inscripción"):
                st.session_state['nueva_inscripcion'] = True
                st.rerun()
    
    def _mostrar_nueva_inscripcion(self, ciclo_actual: str):
        """Mostrar formulario para nueva inscripción"""
        st.subheader("Nueva Inscripción")
        
        # Listar estudiantes activos no inscritos en este ciclo
        estudiantes_activos = self.obtener_estudiantes('Activo', None, 1000)
        
        # Filtrar estudiantes ya inscritos en este ciclo
        inscripciones_actuales = self.obtener_inscripciones(ciclo_escolar=ciclo_actual)
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
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            
            if estudiante:
                st.write(f"**Información del estudiante:**")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"📚 Carrera: {estudiante.get('carrera', 'No especificada')}")
                    st.write(f"🎓 Nivel: {estudiante.get('nivel_estudio', 'No especificado')}")
                with col2:
                    st.write(f"📅 Semestre actual: {estudiante.get('semestre', 'No especificado')}")
                    st.write(f"⭐ Promedio: {estudiante.get('promedio', 'No registrado')}")
                
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
                
                if st.button("📝 Realizar Inscripción"):
                    try:
                        self.inscribir_estudiante(
                            estudiante_id, 
                            ciclo_actual, 
                            semestre_inscripcion, 
                            creditos_inscritos
                        )
                        st.success(f"✅ Estudiante inscrito exitosamente en ciclo {ciclo_actual}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
    
    def _mostrar_estadisticas_inscripciones(self):
        """Mostrar estadísticas de inscripciones"""
        estadisticas = self.obtener_estadisticas_generales()
        
        if estadisticas.get('inscripciones_por_ciclo'):
            st.subheader("📈 Inscripciones por Ciclo Escolar")
            
            df_ciclos = pd.DataFrame(
                list(estadisticas['inscripciones_por_ciclo'].items()),
                columns=['Ciclo Escolar', 'Inscripciones']
            )
            
            st.dataframe(df_ciclos, use_container_width=True)
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
        egresados = self.obtener_egresados(
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
            st.dataframe(df, use_container_width=True)
            
            # Estadísticas de egresados
            st.subheader("📊 Estadísticas de Egresados")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Egresados", len(egresados))
            
            with col2:
                if egresados:
                    promedios = [eg['promedio_final'] or 0 for eg in egresados if eg['promedio_final']]
                    if promedios:
                        promedio_general = sum(promedios) / len(promedios)
                        st.metric("Promedio General", f"{promedio_general:.2f}")
                    else:
                        st.metric("Promedio General", "N/A")
            
            with col3:
                carreras_unicas = len(set(eg['carrera'] for eg in egresados if eg['carrera']))
                st.metric("Carreras", carreras_unicas)
        else:
            st.info("📭 No hay egresados registrados")
            
            # Botón para registrar primer egresado
            if st.button("🎓 Registrar primer egresado"):
                st.session_state['registrar_egresado'] = True
                st.rerun()
    
    def _mostrar_registro_egresado(self):
        """Mostrar formulario para registrar egresado"""
        st.subheader("Registrar Nuevo Egresado")
        
        # Listar estudiantes activos no egresados
        estudiantes_activos = self.obtener_estudiantes('Activo', None, 1000)
        
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
            estudiante = self.obtener_estudiante_por_id(estudiante_id)
            
            if estudiante:
                st.write(f"**Información del estudiante:**")
                st.write(f"📚 Carrera: {estudiante.get('carrera', 'No especificada')}")
                st.write(f"⭐ Promedio actual: {estudiante.get('promedio', 'No registrado')}")
                
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
                
                campos_adicionales = st.expander("📄 Campos Adicionales")
                with campos_adicionales:
                    fecha_titulacion = st.date_input("Fecha de Titulación", value=None)
                    numero_cedula = st.text_input("Número de Cédula", max_chars=50)
                    institucion_titulacion = st.text_input("Institución de Titulación", max_chars=200)
                
                if st.button("🎓 Registrar Egresado"):
                    if not titulo_obtenido:
                        st.error("❌ El título obtenido es obligatorio")
                    elif not fecha_egreso:
                        st.error("❌ La fecha de egreso es obligatoria")
                    else:
                        try:
                            self.registrar_egresado(
                                estudiante_id,
                                fecha_egreso.isoformat(),
                                titulo_obtenido,
                                promedio_final
                            )
                            st.success("✅ Egresado registrado exitosamente")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
    
    def _mostrar_gestion_contrataciones(self):
        """Mostrar gestión de contrataciones"""
        st.subheader("💼 Gestión de Contrataciones")
        
        # Pestañas para contrataciones
        tab1, tab2 = st.tabs(["📋 Contrataciones Registradas", "➕ Nueva Contratación"])
        
        with tab1:
            contratados = self.obtener_contratados()
            
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
                st.dataframe(df, use_container_width=True)
                
                # Estadísticas
                st.subheader("📊 Estadísticas de Contrataciones")
                col1, col2 = st.columns(2)
                
                with col1:
                    empresas_unicas = len(set(cont['empresa'] for cont in contratados))
                    st.metric("Empresas", empresas_unicas)
                
                with col2:
                    egresados_totales = len(self.obtener_egresados())
                    if egresados_totales > 0:
                        tasa_contratacion = (len(contratados) / egresados_totales) * 100
                        st.metric("Tasa de Contratación", f"{tasa_contratacion:.1f}%")
                    else:
                        st.metric("Tasa de Contratación", "N/A")
            else:
                st.info("📭 No hay contrataciones registradas")
        
        with tab2:
            # Formulario para nueva contratación
            egresados = self.obtener_egresados()
            
            if not egresados:
                st.warning("⚠️ No hay egresados registrados")
            else:
                egresado_opciones = {
                    f"{eg['id']} - {eg['matricula']} - {eg['nombre']} {eg['apellido_paterno']}": eg['id']
                    for eg in egresados
                }
                
                egresado_seleccionado = st.selectbox(
                    "Seleccionar egresado:",
                    list(egresado_opciones.keys())
                )
                
                if egresado_seleccionado:
                    egresado_id = egresado_opciones[egresado_seleccionado]
                    
                    # Información del egresado
                    egresado_info = next((eg for eg in egresados if eg['id'] == egresado_id), None)
                    
                    if egresado_info:
                        st.write(f"**Información del egresado:**")
                        st.write(f"🎓 Título: {egresado_info['titulo_obtenido']}")
                        st.write(f"⭐ Promedio: {egresado_info['promedio_final']}")
                        
                        # Formulario de contratación
                        empresa = st.text_input("Empresa *", max_chars=200)
                        puesto = st.text_input("Puesto", max_chars=100)
                        fecha_contratacion = st.date_input("Fecha de Contratación", value=datetime.now())
                        salario_inicial = st.number_input("Salario Inicial", min_value=0.0, value=0.0, step=1000.0)
                        tipo_contrato = st.selectbox(
                            "Tipo de Contrato",
                            ['Indeterminado', 'Temporal', 'Por Obra', 'Honorarios', 'Otro']
                        )
                        
                        if st.button("💼 Registrar Contratación"):
                            if not empresa:
                                st.error("❌ La empresa es obligatoria")
                            else:
                                try:
                                    self.registrar_contratacion(
                                        egresado_id,
                                        empresa,
                                        puesto,
                                        fecha_contratacion.isoformat(),
                                        salario_inicial,
                                        tipo_contrato
                                    )
                                    st.success("✅ Contratación registrada exitosamente")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {e}")
    
    def mostrar_configuracion_sistema(self):
        """Mostrar configuración del sistema"""
        st.title("⚙️ Configuración del Sistema")
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Estado del Sistema",
            "🔄 Sincronización",
            "💾 Backup",
            "🔧 Configuración"
        ])
        
        with tab1:
            self._mostrar_estado_sistema()
        
        with tab2:
            self._mostrar_sincronizacion()
        
        with tab3:
            self._mostrar_backup()
        
        with tab4:
            self._mostrar_configuracion()
    
    def _mostrar_estado_sistema(self):
        """Mostrar estado actual del sistema"""
        st.subheader("📊 Estado del Sistema")
        
        # Información de conexión SSH
        st.write("### 🔗 Estado de Conexión SSH")
        col1, col2 = st.columns(2)
        
        with col1:
            if self.ssh_config.get('enabled', False):
                if self.estado.estado.get('ssh_conectado'):
                    st.success("✅ Conectado al servidor remoto")
                    st.write(f"**Servidor:** {self.ssh_config.get('host', 'Desconocido')}")
                    st.write(f"**Usuario:** {self.ssh_config.get('username', 'Desconocido')}")
                else:
                    st.error("❌ Desconectado del servidor remoto")
                    if self.estado.estado.get('ssh_error'):
                        st.error(f"**Error:** {self.estado.estado['ssh_error']}")
            else:
                st.info("🔌 SSH deshabilitado en configuración")
        
        with col2:
            if self.estado.estado.get('ultima_sincronizacion'):
                fecha_sync = datetime.fromisoformat(self.estado.estado['ultima_sincronizacion'])
                st.write(f"**Última sincronización:** {fecha_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.warning("⚠️ Nunca sincronizado")
            
            if self.estado.estado.get('ultima_verificacion'):
                fecha_ver = datetime.fromisoformat(self.estado.estado['ultima_verificacion'])
                st.write(f"**Última verificación:** {fecha_ver.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Estadísticas de la base de datos
        st.write("### 🗄️ Estadísticas de Base de Datos")
        
        try:
            cursor = self.conexion_local.cursor()
            
            # Contar registros por tabla
            tablas = ['estudiantes', 'inscritos', 'egresados', 'contratados', 'usuarios']
            for tabla in tablas:
                cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
                count = cursor.fetchone()[0]
                st.write(f"**{tabla.capitalize()}:** {count} registros")
            
        except Exception as e:
            st.error(f"❌ Error obteniendo estadísticas: {e}")
        
        # Información de migraciones
        st.write("### 🔄 Estadísticas de Migraciones")
        estadisticas_mig = self.estado.obtener_estadisticas()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Migraciones Exitosas", estadisticas_mig.get('exitosas', 0))
        with col2:
            st.metric("Migraciones Fallidas", estadisticas_mig.get('fallidas', 0))
        with col3:
            st.metric("Backups Realizados", self.estado.estado.get('backups_realizados', 0))
    
    def _mostrar_sincronizacion(self):
        """Mostrar opciones de sincronización"""
        st.subheader("🔄 Sincronización con Servidor")
        
        st.info("""
        La sincronización descarga la base de datos más reciente del servidor remoto
        y sube los cambios locales. Esto asegura que siempre trabajes con la información
        más actualizada.
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 Sincronizar desde Servidor", type="primary"):
                with st.spinner("🔄 Sincronizando..."):
                    if self.sincronizar_con_servidor():
                        st.success("✅ Sincronización completada")
                        st.rerun()
                    else:
                        st.error("❌ Error en sincronización")
        
        with col2:
            if st.button("🔼 Subir Cambios al Servidor"):
                with st.spinner("🔼 Subiendo cambios..."):
                    if self.subir_cambios_al_servidor():
                        st.success("✅ Cambios subidos exitosamente")
                    else:
                        st.error("❌ Error subiendo cambios")
        
        # Información de conexión
        st.write("### 🔗 Configuración de Conexión")
        if self.ssh_config.get('enabled', False):
            st.json({
                "host": self.ssh_config.get('host'),
                "port": self.ssh_config.get('port'),
                "username": self.ssh_config.get('username'),
                "remote_dir": self.ssh_config.get('remote_dir', ''),
                "escuela_db": self.rutas.get('escuela_db', ''),
                "inscritos_db": self.rutas.get('inscritos_db', '')
            })
        else:
            st.info("SSH deshabilitado en configuración")
    
    def _mostrar_backup(self):
        """Mostrar opciones de backup"""
        st.subheader("💾 Sistema de Backup")
        
        st.info("""
        Los backups se crean automáticamente antes de operaciones críticas.
        También puedes crear backups manuales en cualquier momento.
        """)
        
        # Crear backup manual
        if st.button("💾 Crear Backup Manual", type="primary"):
            with st.spinner("Creando backup..."):
                if self.crear_backup():
                    st.success("✅ Backup creado exitosamente")
                else:
                    st.error("❌ Error creando backup")
        
        # Listar backups existentes
        st.write("### 📦 Backups Existentes")
        
        try:
            import tempfile
            temp_dir = tempfile.gettempdir()
            backup_dir = os.path.join(temp_dir, self.config.get('backup_dir', 'backups_escuela'))
            
            if os.path.exists(backup_dir):
                backups = []
                for file in os.listdir(backup_dir):
                    if file.startswith('escuela_backup_'):
                        file_path = os.path.join(backup_dir, file)
                        if os.path.isfile(file_path):
                            size_mb = os.path.getsize(file_path) / (1024 * 1024)
                            mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                            backups.append({
                                'Archivo': file,
                                'Tamaño (MB)': f"{size_mb:.2f}",
                                'Fecha': mtime.strftime('%Y-%m-%d %H:%M:%S')
                            })
                
                if backups:
                    df_backups = pd.DataFrame(backups)
                    st.dataframe(df_backups, use_container_width=True)
                    
                    # Opción para descargar backup
                    backup_seleccionado = st.selectbox(
                        "Seleccionar backup para descargar:",
                        [f"{b['Archivo']} ({b['Fecha']})" for b in backups]
                    )
                    
                    if backup_seleccionado and st.button("⬇️ Descargar Backup"):
                        # Aquí iría la lógica para descargar el backup
                        st.info("⚠️ Función de descarga en desarrollo")
                else:
                    st.info("📭 No hay backups creados")
            else:
                st.info("📭 Directorio de backups no existe")
        except Exception as e:
            st.error(f"❌ Error listando backups: {e}")
    
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
                    value=PAGE_SIZE
                )
                
                nuevo_cache_ttl = st.number_input(
                    "TTL de caché (segundos):",
                    min_value=60,
                    max_value=3600,
                    value=CACHE_TTL
                )
            
            with col2:
                auto_sync = st.checkbox(
                    "Sincronización automática al iniciar",
                    value=self.config.get('sync_on_start', False)
                )
                
                auto_connect = st.checkbox(
                    "Conexión automática SSH",
                    value=self.config.get('auto_connect', False)
                )
            
            if st.button("💾 Guardar Configuración"):
                # Aquí se guardaría la configuración en un archivo
                st.success("✅ Configuración guardada (en sesión)")
        
        # Configuración de backup
        with st.expander("💾 Configuración de Backup"):
            col1, col2 = st.columns(2)
            
            with col1:
                max_backups = st.number_input(
                    "Máximo de backups a mantener:",
                    min_value=1,
                    max_value=50,
                    value=self.config.get('backup', {}).get('max_backups', 10)
                )
                
                min_space = st.number_input(
                    "Espacio mínimo requerido (MB):",
                    min_value=10,
                    max_value=1000,
                    value=self.config.get('backup', {}).get('min_disk_space_mb', 100)
                )
            
            with col2:
                backup_enabled = st.checkbox(
                    "Habilitar sistema de backup",
                    value=self.config.get('backup', {}).get('enabled', True)
                )
                
                auto_backup = st.checkbox(
                    "Backup automático antes de operaciones críticas",
                    value=self.config.get('backup', {}).get('auto_backup_before_migration', True)
                )
        
        # Limpiar caché
        with st.expander("🗑️ Mantenimiento"):
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🧹 Limpiar Caché"):
                    self.limpiar_cache()
                    st.success("✅ Caché limpiado")
            
            with col2:
                if st.button("🔄 Reinicializar Base de Datos"):
                    if st.checkbox("¿Confirmar reinicialización? Esto eliminará todos los datos locales."):
                        try:
                            self._inicializar_base_datos()
                            st.success("✅ Base de datos reinicializada")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")

# =============================================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN - CORREGIDA
# =============================================================================

def main():
    """Función principal de la aplicación"""
    
    # Configurar página de Streamlit
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon=APP_ICON,
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Inicializar variables de sesión
    if 'sistema' not in st.session_state:
        st.session_state.sistema = None
    if 'inicializado' not in st.session_state:
        st.session_state.inicializado = False
    
    # Verificar importaciones
    if not IMPORTACIONES_COMPARTIDAS:
        st.error("""
        ❌ **Error crítico: Módulos compartidos no encontrados**
        
        Verifica que:
        1. `shared_config.py` esté en el mismo directorio
        2. Todas las dependencias estén instaladas (ver requirements.txt)
        3. Reinicia la aplicación
        """)
        return
    
    # Inicializar sistema
    if not st.session_state.inicializado:
        with st.spinner("🚀 Inicializando Sistema de Gestión Escolar..."):
            try:
                sistema = SistemaGestionEscolar()
                st.session_state.sistema = sistema
                st.session_state.inicializado = True
                logger.info("✅ Sistema de Gestión Escolar inicializado")
                
            except Exception as e:
                st.error(f"❌ Error crítico al inicializar el sistema: {e}")
                logger.error(f"❌ Error inicializando sistema: {e}")
                
                # Mostrar información de diagnóstico
                with st.expander("🔧 Información de diagnóstico"):
                    st.write(f"**Error:** {str(e)}")
                    st.write(f"**Configuración SSH habilitada:** {config.get('ssh', {}).get('enabled', False)}")
                    st.write(f"**Ruta BD local:** {sistema.db_local_path if 'sistema' in locals() else 'No creada'}")
                
                return
    
    sistema = st.session_state.sistema
    
    # Barra lateral con navegación
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2784/2784449.png", width=100)
        st.title(APP_TITLE)
        st.markdown("---")
        
        # Estado del sistema
        st.subheader("📊 Estado del Sistema")
        if sistema.estado.esta_inicializada():
            st.success("✅ Sistema listo")
            if sistema.ssh_config.get('enabled', False):
                if sistema.estado.estado.get('ssh_conectado'):
                    st.success("🔗 Conectado al servidor")
                else:
                    st.error("❌ Desconectado del servidor")
            else:
                st.info("🔌 SSH deshabilitado")
        else:
            st.error("❌ Sistema no inicializado")
        
        st.markdown("---")
        
        # Navegación
        st.subheader("🧭 Navegación")
        opcion = st.radio(
            "Seleccionar módulo:",
            [
                "🏠 Panel de Control",
                "👨‍🎓 Gestión de Estudiantes",
                "📝 Gestión de Inscripciones",
                "🎓 Gestión de Egresados",
                "💼 Seguimiento de Contratados",
                "⚙️ Configuración del Sistema"
            ]
        )
        
        st.markdown("---")
        
        # Acciones rápidas
        st.subheader("⚡ Acciones Rápidas")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Sincronizar"):
                with st.spinner("Sincronizando..."):
                    if sistema.sincronizar_con_servidor():
                        st.success("✅ Sincronizado")
                        st.rerun()
                    else:
                        st.error("❌ Error")
        
        with col2:
            if st.button("💾 Backup"):
                with st.spinner("Creando backup..."):
                    if sistema.crear_backup():
                        st.success("✅ Backup creado")
                    else:
                        st.error("❌ Error")
        
        st.markdown("---")
        
        # Información del sistema
        estadisticas = sistema.obtener_estadisticas_generales()
        st.caption(f"Versión: 3.0 (Streamlit Cloud)")
        st.caption(f"Última sync: {sistema.estado.estado.get('ultima_sincronizacion', 'Nunca')[:19]}")
        st.caption(f"Estudiantes: {estadisticas.get('total_estudiantes', 0)}")
        st.caption(f"BD: {os.path.basename(sistema.db_local_path) if sistema.db_local_path else 'Memoria'}")
    
    # Contenido principal basado en la selección
    if opcion == "🏠 Panel de Control":
        sistema.mostrar_panel_control()
    
    elif opcion == "👨‍🎓 Gestión de Estudiantes":
        sistema.mostrar_gestion_estudiantes()
    
    elif opcion == "📝 Gestión de Inscripciones":
        sistema.mostrar_gestion_inscripciones()
    
    elif opcion == "🎓 Gestión de Egresados":
        sistema.mostrar_gestion_egresados()
    
    elif opcion == "💼 Seguimiento de Contratados":
        # Por ahora, redirigir a gestión de egresados que incluye contrataciones
        sistema.mostrar_gestion_egresados()
    
    elif opcion == "⚙️ Configuración del Sistema":
        sistema.mostrar_configuracion_sistema()
    
    # Pie de página
    st.markdown("---")
    st.caption(f"© 2024 Sistema de Gestión Escolar v3.0 | Modo: {'SSH' if sistema.ssh_config.get('enabled', False) else 'Local'} | BD: {sistema.db_local_path}")

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    main()
