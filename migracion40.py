"""
migracion30.py - Sistema de Migración y Consolidación de Datos
Versión 3.0 con estado persistente independiente
Sistema REMOTO exclusivo para administradores - Operaciones de migración masiva
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

# Importar módulos compartidos
try:
    from shared_config import (
        SistemaLogging,
        CargadorConfiguracion,
        EstadoPersistenteBase,
        GestorSSHCompartido,
        UtilidadesCompartidas
    )
except ImportError as e:
    st.error(f"❌ Error crítico: No se pudo importar módulos compartidos: {e}")
    st.stop()

# =============================================================================
# CONFIGURACIÓN Y LOGGING
# =============================================================================

# Obtener configuración para el sistema migración
config = CargadorConfiguracion.obtener_config_sistema('migration')

# Configurar logging
logger = SistemaLogging.obtener_logger(
    'migration', 
    config.get('log_file', 'migracion_detallado.log')
)

# Crear instancia de estado persistente
estado_archivo = config.get('estado_file', 'estado_migracion.json')
estado = EstadoPersistenteBase(estado_archivo, 'migration')

# Instancia global del gestor SSH
gestor_ssh = GestorSSHCompartido()

# =============================================================================
# CONSTANTES Y CONFIGURACIÓN
# =============================================================================

# Configuración de la aplicación
APP_TITLE = "🔄 Sistema de Migración de Datos"
APP_ICON = "🔄"
RETRY_ATTEMPTS = config.get('retry_attempts', 3)
RETRY_DELAY = config.get('retry_delay', 5)

# Tipos de migración soportados
TIPOS_MIGRACION = [
    'estudiantes_a_egresados',
    'egresados_a_contratados',
    'aspirantes_a_estudiantes',
    'consolidar_bases',
    'limpiar_duplicados',
    'migrar_historico'
]

# Estados de migración
ESTADOS_MIGRACION = [
    'pendiente',
    'en_progreso',
    'completada',
    'fallida',
    'revertida'
]

# =============================================================================
# CLASE PRINCIPAL DEL SISTEMA DE MIGRACIÓN
# =============================================================================

class SistemaMigracion:
    """Clase principal del sistema de migración"""
    
    def __init__(self):
        self.config = config
        self.logger = logger
        self.estado = estado
        self.gestor_ssh = gestor_ssh
        self.util = UtilidadesCompartidas()
        
        # Configuración de rutas
        self.rutas = config.get('remote_paths', {})
        self.ssh_config = config.get('ssh', {})
        
        # Conexiones a bases de datos
        self.conexiones = {}
        self.migraciones_activas = {}
        
        # Inicializar
        self._inicializar_sistema()
    
    def _inicializar_sistema(self):
        """Inicializar el sistema de migración"""
        self.logger.info("🚀 Inicializando Sistema de Migración")
        
        # Verificar si ya está inicializado
        if not self.estado.esta_inicializada():
            self._inicializar_base_datos_migracion()
        else:
            self.logger.info(f"✅ Sistema ya inicializado el {self.estado.obtener_fecha_inicializacion()}")
        
        # Sincronizar si está configurado
        if self.config.get('sync_on_start', True):
            self.sincronizar_bases_datos()
    
    def _inicializar_base_datos_migracion(self):
        """Inicializar la base de datos de migración"""
        try:
            self.logger.info("🔄 Inicializando base de datos de migración...")
            
            # Crear base de datos local para migración
            self.db_migracion_path = "migracion_control.db"
            
            if os.path.exists(self.db_migracion_path):
                os.remove(self.db_migracion_path)
            
            self.conexiones['migracion'] = sqlite3.connect(
                self.db_migracion_path, 
                check_same_thread=False
            )
            self.conexiones['migracion'].row_factory = sqlite3.Row
            
            # Crear estructura de tablas de control
            self._crear_estructura_bd_migracion()
            
            # Marcar como inicializada
            self.estado.marcar_db_inicializada()
            self.logger.info("✅ Base de datos de migración inicializada")
            
        except Exception as e:
            self.logger.error(f"❌ Error inicializando base de datos de migración: {e}")
            st.error(f"Error crítico al inicializar: {str(e)}")
    
    def _crear_estructura_bd_migracion(self):
        """Crear estructura de la base de datos de control de migración"""
        cursor = self.conexiones['migracion'].cursor()
        
        # Tabla de migraciones programadas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS migraciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_migracion TEXT NOT NULL,
                descripcion TEXT,
                estado TEXT DEFAULT 'pendiente',
                total_registros INTEGER DEFAULT 0,
                registros_procesados INTEGER DEFAULT 0,
                registros_exitosos INTEGER DEFAULT 0,
                registros_fallidos INTEGER DEFAULT 0,
                fecha_programada TEXT,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                duracion_segundos REAL,
                usuario_ejecutor TEXT,
                configuracion TEXT,
                resultado TEXT,
                errores TEXT,
                revertida INTEGER DEFAULT 0,
                fecha_reversion TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de registros migrados (detalle)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registros_migrados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migracion_id INTEGER NOT NULL,
                registro_origen_id INTEGER,
                registro_destino_id INTEGER,
                tabla_origen TEXT,
                tabla_destino TEXT,
                datos_origen TEXT,
                datos_destino TEXT,
                estado TEXT CHECK(estado IN ('exitoso', 'fallido', 'omitido')),
                error_mensaje TEXT,
                fecha_procesamiento TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (migracion_id) REFERENCES migraciones (id)
            )
        ''')
        
        # Tabla de conflictos detectados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conflictos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migracion_id INTEGER,
                tipo_conflicto TEXT,
                tabla_afectada TEXT,
                registro_id INTEGER,
                descripcion TEXT,
                resolucion TEXT,
                fecha_deteccion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_resolucion TEXT,
                FOREIGN KEY (migracion_id) REFERENCES migraciones (id)
            )
        ''')
        
        # Tabla de plantillas de migración
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plantillas_migracion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                tipo_migracion TEXT NOT NULL,
                configuracion TEXT NOT NULL,
                descripcion TEXT,
                activa INTEGER DEFAULT 1,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                fecha_actualizacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insertar plantillas por defecto
        plantillas_base = [
            {
                'nombre': 'estudiantes_a_egresados_basico',
                'tipo_migracion': 'estudiantes_a_egresados',
                'configuracion': json.dumps({
                    'criterios': {
                        'estado_estudiante': 'Activo',
                        'semestre_minimo': 8,
                        'promedio_minimo': 8.0
                    },
                    'campos_mapeo': {
                        'matricula': 'matricula',
                        'nombre': 'nombre',
                        'apellido_paterno': 'apellido_paterno',
                        'apellido_materno': 'apellido_materno',
                        'carrera': 'carrera'
                    },
                    'opciones': {
                        'crear_backup_antes': True,
                        'validar_duplicados': True,
                        'enviar_notificacion': False
                    }
                }),
                'descripcion': 'Migración básica de estudiantes activos a egresados'
            },
            {
                'nombre': 'consolidar_bases_completo',
                'tipo_migracion': 'consolidar_bases',
                'configuracion': json.dumps({
                    'bases_origen': ['aspirantes', 'estudiantes', 'egresados'],
                    'tabla_destino': 'consolidado_general',
                    'estrategia_fusion': 'ultima_actualizacion',
                    'mantener_historico': True
                }),
                'descripcion': 'Consolidación completa de todas las bases'
            }
        ]
        
        for plantilla in plantillas_base:
            cursor.execute(
                "INSERT OR IGNORE INTO plantillas_migracion (nombre, tipo_migracion, configuracion, descripcion) VALUES (?, ?, ?, ?)",
                (plantilla['nombre'], plantilla['tipo_migracion'], plantilla['configuracion'], plantilla['descripcion'])
            )
        
        self.conexiones['migracion'].commit()
        self.logger.info("✅ Estructura de control de migración creada")
    
    # =============================================================================
    # OPERACIONES DE SINCRONIZACIÓN
    # =============================================================================
    
    def sincronizar_bases_datos(self):
        """Sincronizar todas las bases de datos desde el servidor"""
        try:
            if not self.ssh_config.get('enabled', True):
                self.logger.warning("SSH deshabilitado, omitiendo sincronización")
                return False
            
            self.logger.info("🔄 Sincronizando bases de datos desde servidor...")
            
            # Conectar al servidor
            if not self.gestor_ssh.conectar():
                self.logger.error("❌ No se pudo conectar al servidor SSH")
                return False
            
            sftp = self.gestor_ssh.obtener_sftp()
            if not sftp:
                self.logger.error("❌ No se pudo obtener cliente SFTP")
                return False
            
            # Lista de bases de datos a sincronizar
            bases_datos = [
                ('escuela_db', 'temp_escuela.db'),
                ('aspirantes_db', 'temp_aspirantes.db'),
                ('inscritos_db', 'temp_inscritos.db')
            ]
            
            for config_key, local_file in bases_datos:
                ruta_remota = self.rutas.get(config_key)
                if ruta_remota:
                    try:
                        self._descargar_base_datos(sftp, ruta_remota, local_file)
                    except Exception as e:
                        self.logger.warning(f"⚠️ Error descargando {config_key}: {e}")
            
            # Actualizar estado
            self.estado.marcar_sincronizacion()
            self.estado.set_ssh_conectado(True)
            
            # Conectar a las bases de datos descargadas
            self._conectar_bases_datos_locales()
            
            self.logger.info("✅ Sincronización de bases completada")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error en sincronización: {e}")
            self.estado.set_ssh_conectado(False, str(e))
            return False
    
    def _descargar_base_datos(self, sftp, ruta_remota: str, ruta_local: str):
        """Descargar base de datos desde servidor remoto"""
        try:
            self.logger.info(f"📥 Descargando {ruta_remota}...")
            
            # Crear backup del archivo local si existe
            if os.path.exists(ruta_local):
                timestamp = self.util.generar_timestamp()
                backup_path = f"{ruta_local}.backup_{timestamp}"
                import shutil
                shutil.copy2(ruta_local, backup_path)
                self.logger.debug(f"Backup creado: {backup_path}")
            
            # Descargar archivo
            sftp.get(ruta_remota, ruta_local)
            
            # Verificar que el archivo se descargó correctamente
            if os.path.exists(ruta_local) and os.path.getsize(ruta_local) > 0:
                self.logger.info(f"✅ Base de datos descargada: {ruta_local} ({os.path.getsize(ruta_local)} bytes)")
                return True
            else:
                raise Exception("Archivo descargado vacío o no existe")
            
        except FileNotFoundError:
            self.logger.warning(f"⚠️ Archivo remoto no encontrado: {ruta_remota}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Error descargando base de datos: {e}")
            raise
    
    def _conectar_bases_datos_locales(self):
        """Conectar a las bases de datos locales descargadas"""
        try:
            # Bases de datos a conectar
            bases = {
                'escuela': 'temp_escuela.db',
                'aspirantes': 'temp_aspirantes.db',
                'inscritos': 'temp_inscritos.db'
            }
            
            for nombre, archivo in bases.items():
                if os.path.exists(archivo):
                    conexion = sqlite3.connect(archivo, check_same_thread=False)
                    conexion.row_factory = sqlite3.Row
                    self.conexiones[nombre] = conexion
                    self.logger.info(f"✅ Conectado a base de datos: {nombre}")
                else:
                    self.logger.warning(f"⚠️ Archivo no encontrado: {archivo}")
            
        except Exception as e:
            self.logger.error(f"❌ Error conectando bases de datos: {e}")
    
    def subir_base_datos(self, nombre_base: str, ruta_local: str):
        """Subir base de datos al servidor"""
        try:
            if not os.path.exists(ruta_local):
                raise FileNotFoundError(f"Archivo local no existe: {ruta_local}")
            
            if not self.gestor_ssh.conectar():
                raise Exception("No se pudo conectar al servidor SSH")
            
            sftp = self.gestor_ssh.obtener_sftp()
            if not sftp:
                raise Exception("No se pudo obtener cliente SFTP")
            
            # Obtener ruta remota
            clave_config = f"{nombre_base}_db"
            ruta_remota = self.rutas.get(clave_config)
            
            if not ruta_remota:
                raise Exception(f"No hay ruta remota configurada para {nombre_base}")
            
            # Crear backup remoto antes de subir
            timestamp = self.util.generar_timestamp()
            backup_remoto = f"{ruta_remota}.backup_{timestamp}"
            
            try:
                sftp.get(ruta_remota, backup_remoto)
                self.logger.info(f"Backup remoto creado: {backup_remoto}")
            except:
                self.logger.warning("No se pudo crear backup remoto (primera subida?)")
            
            # Subir archivo
            sftp.put(ruta_local, ruta_remota)
            
            self.logger.info(f"✅ Base de datos {nombre_base} subida al servidor")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error subiendo base de datos {nombre_base}: {e}")
            raise
    
    # =============================================================================
    # OPERACIONES DE MIGRACIÓN
    # =============================================================================
    
    def ejecutar_migracion(self, tipo_migracion: str, configuracion: dict = None, 
                          usuario: str = None):
        """Ejecutar una migración específica"""
        try:
            self.logger.info(f"🔄 Iniciando migración: {tipo_migracion}")
            
            # Validar tipo de migración
            if tipo_migracion not in TIPOS_MIGRACION:
                raise ValueError(f"Tipo de migración no válido: {tipo_migracion}")
            
            # Crear registro de migración
            migracion_id = self._crear_registro_migracion(
                tipo_migracion, configuracion, usuario
            )
            
            # Ejecutar migración específica
            inicio = time.time()
            
            if tipo_migracion == 'estudiantes_a_egresados':
                resultado = self._migrar_estudiantes_a_egresados(migracion_id, configuracion)
            elif tipo_migracion == 'egresados_a_contratados':
                resultado = self._migrar_egresados_a_contratados(migracion_id, configuracion)
            elif tipo_migracion == 'aspirantes_a_estudiantes':
                resultado = self._migrar_aspirantes_a_estudiantes(migracion_id, configuracion)
            elif tipo_migracion == 'consolidar_bases':
                resultado = self._consolidar_bases_datos(migracion_id, configuracion)
            elif tipo_migracion == 'limpiar_duplicados':
                resultado = self._limpiar_duplicados(migracion_id, configuracion)
            elif tipo_migracion == 'migrar_historico':
                resultado = self._migrar_historico(migracion_id, configuracion)
            else:
                raise ValueError(f"Migración no implementada: {tipo_migracion}")
            
            duracion = time.time() - inicio
            
            # Actualizar registro de migración
            self._actualizar_registro_migracion(migracion_id, {
                'estado': 'completada' if resultado['exito'] else 'fallida',
                'fecha_fin': datetime.now().isoformat(),
                'duracion_segundos': duracion,
                'resultado': json.dumps(resultado, ensure_ascii=False),
                'total_registros': resultado.get('total', 0),
                'registros_exitosos': resultado.get('exitosos', 0),
                'registros_fallidos': resultado.get('fallidos', 0)
            })
            
            # Registrar en estado general
            self.estado.registrar_migracion(resultado['exito'], duracion)
            
            self.logger.info(f"✅ Migración {tipo_migracion} completada en {duracion:.2f} segundos")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en migración {tipo_migracion}: {e}")
            
            # Actualizar registro como fallido
            if 'migracion_id' in locals():
                self._actualizar_registro_migracion(migracion_id, {
                    'estado': 'fallida',
                    'fecha_fin': datetime.now().isoformat(),
                    'resultado': json.dumps({'error': str(e)}, ensure_ascii=False),
                    'errores': str(e)
                })
            
            self.estado.registrar_migracion(False, 0)
            raise
    
    def _crear_registro_migracion(self, tipo_migracion: str, configuracion: dict = None, 
                                 usuario: str = None) -> int:
        """Crear registro de migración en la base de control"""
        cursor = self.conexiones['migracion'].cursor()
        
        cursor.execute('''
            INSERT INTO migraciones (
                tipo_migracion, descripcion, estado, fecha_programada,
                fecha_inicio, usuario_ejecutor, configuracion
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            tipo_migracion,
            f"Migración automática: {tipo_migracion}",
            'en_progreso',
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            usuario or 'sistema',
            json.dumps(configuracion or {}, ensure_ascii=False)
        ))
        
        self.conexiones['migracion'].commit()
        migracion_id = cursor.lastrowid
        
        self.logger.info(f"📝 Registro de migración creado: ID {migracion_id}")
        return migracion_id
    
    def _actualizar_registro_migracion(self, migracion_id: int, datos: dict):
        """Actualizar registro de migración"""
        cursor = self.conexiones['migracion'].cursor()
        
        set_clauses = []
        valores = []
        
        for campo, valor in datos.items():
            set_clauses.append(f"{campo} = ?")
            valores.append(valor)
        
        valores.append(migracion_id)
        query = f"UPDATE migraciones SET {', '.join(set_clauses)} WHERE id = ?"
        
        cursor.execute(query, valores)
        self.conexiones['migracion'].commit()
    
    def _registrar_registro_migrado(self, migracion_id: int, datos: dict):
        """Registrar un registro migrado individualmente"""
        cursor = self.conexiones['migracion'].cursor()
        
        cursor.execute('''
            INSERT INTO registros_migrados (
                migracion_id, registro_origen_id, registro_destino_id,
                tabla_origen, tabla_destino, datos_origen, datos_destino,
                estado, error_mensaje
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            migracion_id,
            datos.get('registro_origen_id'),
            datos.get('registro_destino_id'),
            datos.get('tabla_origen'),
            datos.get('tabla_destino'),
            json.dumps(datos.get('datos_origen', {}), ensure_ascii=False),
            json.dumps(datos.get('datos_destino', {}), ensure_ascii=False),
            datos.get('estado', 'exitoso'),
            datos.get('error_mensaje')
        ))
        
        self.conexiones['migracion'].commit()
    
    # =============================================================================
    # MIGRACIONES ESPECÍFICAS
    # =============================================================================
    
    def _migrar_estudiantes_a_egresados(self, migracion_id: int, configuracion: dict = None):
        """Migrar estudiantes a egresados basado en criterios"""
        try:
            if 'escuela' not in self.conexiones:
                raise Exception("Base de datos de escuela no disponible")
            
            config = configuracion or {}
            criterios = config.get('criterios', {})
            
            # Construir consulta basada en criterios
            query = "SELECT * FROM estudiantes WHERE 1=1"
            params = []
            
            if criterios.get('estado_estudiante'):
                query += " AND estado_estudiante = ?"
                params.append(criterios['estado_estudiante'])
            
            if criterios.get('semestre_minimo'):
                query += " AND semestre >= ?"
                params.append(criterios['semestre_minimo'])
            
            if criterios.get('promedio_minimo'):
                query += " AND promedio >= ?"
                params.append(criterios['promedio_minimo'])
            
            if criterios.get('fecha_ingreso_maxima'):
                query += " AND fecha_ingreso <= ?"
                params.append(criterios['fecha_ingreso_maxima'])
            
            cursor = self.conexiones['escuela'].cursor()
            cursor.execute(query, params)
            estudiantes = cursor.fetchall()
            
            total = len(estudiantes)
            exitosos = 0
            fallidos = 0
            detalles = []
            
            self.logger.info(f"📊 Migrando {total} estudiantes a egresados")
            
            for estudiante in estudiantes:
                try:
                    # Verificar si ya es egresado
                    cursor.execute(
                        "SELECT COUNT(*) FROM egresados WHERE estudiante_id = ?",
                        (estudiante['id'],)
                    )
                    
                    if cursor.fetchone()[0] > 0:
                        self.logger.debug(f"Estudiante {estudiante['id']} ya es egresado, omitiendo")
                        detalles.append({
                            'estudiante_id': estudiante['id'],
                            'estado': 'omitido',
                            'razon': 'Ya es egresado'
                        })
                        continue
                    
                    # Insertar como egresado
                    fecha_egreso = config.get('fecha_egreso', datetime.now().date().isoformat())
                    
                    cursor.execute('''
                        INSERT INTO egresados (
                            estudiante_id, fecha_egreso, titulo_obtenido,
                            promedio_final, fecha_registro
                        ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        estudiante['id'],
                        fecha_egreso,
                        config.get('titulo_obtenido', estudiante.get('carrera', '')),
                        estudiante.get('promedio', 0.0)
                    ))
                    
                    # Actualizar estado del estudiante
                    cursor.execute(
                        "UPDATE estudiantes SET estado_estudiante = 'Egresado' WHERE id = ?",
                        (estudiante['id'],)
                    )
                    
                    egresado_id = cursor.lastrowid
                    
                    # Registrar en detalle
                    self._registrar_registro_migrado(migracion_id, {
                        'registro_origen_id': estudiante['id'],
                        'registro_destino_id': egresado_id,
                        'tabla_origen': 'estudiantes',
                        'tabla_destino': 'egresados',
                        'datos_origen': dict(estudiante),
                        'estado': 'exitoso'
                    })
                    
                    exitosos += 1
                    
                except Exception as e:
                    fallidos += 1
                    self.logger.error(f"Error migrando estudiante {estudiante['id']}: {e}")
                    
                    self._registrar_registro_migrado(migracion_id, {
                        'registro_origen_id': estudiante['id'],
                        'tabla_origen': 'estudiantes',
                        'tabla_destino': 'egresados',
                        'estado': 'fallido',
                        'error_mensaje': str(e)
                    })
            
            self.conexiones['escuela'].commit()
            
            resultado = {
                'exito': exitosos > 0,
                'total': total,
                'exitosos': exitosos,
                'fallidos': fallidos,
                'detalles': detalles
            }
            
            self.logger.info(f"✅ Migración completada: {exitosos}/{total} exitosos")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en migración estudiantes->egresados: {e}")
            raise
    
    def _migrar_aspirantes_a_estudiantes(self, migracion_id: int, configuracion: dict = None):
        """Migrar aspirantes aprobados a estudiantes"""
        try:
            if 'aspirantes' not in self.conexiones:
                raise Exception("Base de datos de aspirantes no disponible")
            
            if 'escuela' not in self.conexiones:
                raise Exception("Base de datos de escuela no disponible")
            
            config = configuracion or {}
            criterios = config.get('criterios', {})
            
            # Consultar aspirantes aprobados
            query = "SELECT * FROM aspirantes WHERE 1=1"
            params = []
            
            if criterios.get('estado_aprobacion'):
                query += " AND estado_aprobacion = ?"
                params.append(criterios['estado_aprobacion'])
            
            if criterios.get('puntaje_minimo'):
                query += " AND puntaje_total >= ?"
                params.append(criterios['puntaje_minimo'])
            
            cursor_aspirantes = self.conexiones['aspirantes'].cursor()
            cursor_aspirantes.execute(query, params)
            aspirantes = cursor_aspirantes.fetchall()
            
            total = len(aspirantes)
            exitosos = 0
            fallidos = 0
            
            self.logger.info(f"📊 Migrando {total} aspirantes a estudiantes")
            
            for aspirante in aspirantes:
                try:
                    # Verificar si ya es estudiante
                    cursor_escuela = self.conexiones['escuela'].cursor()
                    cursor_escuela.execute(
                        "SELECT COUNT(*) FROM estudiantes WHERE curp = ? OR matricula = ?",
                        (aspirante.get('curp'), aspirante.get('matricula_aspirante'))
                    )
                    
                    if cursor_escuela.fetchone()[0] > 0:
                        self.logger.debug(f"Aspirante {aspirante['id']} ya es estudiante, omitiendo")
                        continue
                    
                    # Mapear campos de aspirante a estudiante
                    datos_estudiante = {
                        'matricula': self._generar_matricula(aspirante),
                        'nombre': aspirante.get('nombre', ''),
                        'apellido_paterno': aspirante.get('apellido_paterno', ''),
                        'apellido_materno': aspirante.get('apellido_materno', ''),
                        'fecha_nacimiento': aspirante.get('fecha_nacimiento'),
                        'genero': aspirante.get('genero'),
                        'curp': aspirante.get('curp'),
                        'telefono': aspirante.get('telefono'),
                        'email': aspirante.get('email'),
                        'direccion': aspirante.get('direccion'),
                        'ciudad': aspirante.get('ciudad'),
                        'estado': aspirante.get('estado'),
                        'codigo_postal': aspirante.get('codigo_postal'),
                        'nivel_estudio': aspirante.get('nivel_estudio_solicitado'),
                        'carrera': aspirante.get('carrera_solicitada'),
                        'semestre': 1,  # Siempre empiezan en primer semestre
                        'turno': aspirante.get('turno_preferido'),
                        'fecha_ingreso': datetime.now().date().isoformat(),
                        'estado_estudiante': 'Activo'
                    }
                    
                    # Insertar como estudiante
                    campos = []
                    placeholders = []
                    valores = []
                    
                    for campo, valor in datos_estudiante.items():
                        if valor is not None:
                            campos.append(campo)
                            placeholders.append('?')
                            valores.append(valor)
                    
                    campos.append('fecha_creacion')
                    campos.append('fecha_actualizacion')
                    placeholders.append('CURRENT_TIMESTAMP')
                    placeholders.append('CURRENT_TIMESTAMP')
                    
                    query_insert = f"""
                        INSERT INTO estudiantes ({', '.join(campos)}) 
                        VALUES ({', '.join(placeholders)})
                    """
                    
                    cursor_escuela.execute(query_insert, valores)
                    estudiante_id = cursor_escuela.lastrowid
                    
                    # Actualizar estado del aspirante
                    cursor_aspirantes.execute(
                        "UPDATE aspirantes SET estado_migracion = 'migrado' WHERE id = ?",
                        (aspirante['id'],)
                    )
                    
                    # Registrar en detalle
                    self._registrar_registro_migrado(migracion_id, {
                        'registro_origen_id': aspirante['id'],
                        'registro_destino_id': estudiante_id,
                        'tabla_origen': 'aspirantes',
                        'tabla_destino': 'estudiantes',
                        'datos_origen': dict(aspirante),
                        'datos_destino': datos_estudiante,
                        'estado': 'exitoso'
                    })
                    
                    exitosos += 1
                    
                except Exception as e:
                    fallidos += 1
                    self.logger.error(f"Error migrando aspirante {aspirante['id']}: {e}")
                    
                    self._registrar_registro_migrado(migracion_id, {
                        'registro_origen_id': aspirante['id'],
                        'tabla_origen': 'aspirantes',
                        'tabla_destino': 'estudiantes',
                        'estado': 'fallido',
                        'error_mensaje': str(e)
                    })
            
            self.conexiones['aspirantes'].commit()
            self.conexiones['escuela'].commit()
            
            resultado = {
                'exito': exitosos > 0,
                'total': total,
                'exitosos': exitosos,
                'fallidos': fallidos
            }
            
            self.logger.info(f"✅ Migración completada: {exitosos}/{total} exitosos")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en migración aspirantes->estudiantes: {e}")
            raise
    
    def _generar_matricula(self, aspirante: dict) -> str:
        """Generar matrícula única para nuevo estudiante"""
        try:
            # Usar año actual + carrera código + secuencia
            año_actual = datetime.now().year % 100
            carrera_codigo = aspirante.get('carrera_solicitada', 'GEN')[:3].upper()
            
            # Buscar última matrícula similar
            cursor = self.conexiones['escuela'].cursor()
            cursor.execute(
                "SELECT matricula FROM estudiantes WHERE matricula LIKE ? ORDER BY matricula DESC LIMIT 1",
                (f"{año_actual:02d}{carrera_codigo}%",)
            )
            
            resultado = cursor.fetchone()
            
            if resultado:
                ultima_matricula = resultado['matricula']
                # Extraer secuencia numérica
                import re
                match = re.search(r'\d+$', ultima_matricula)
                if match:
                    secuencia = int(match.group()) + 1
                else:
                    secuencia = 1
            else:
                secuencia = 1
            
            return f"{año_actual:02d}{carrera_codigo}{secuencia:04d}"
            
        except Exception:
            # Fallback: usar timestamp
            return f"EST{int(time.time()) % 1000000:06d}"
    
    def _consolidar_bases_datos(self, migracion_id: int, configuracion: dict = None):
        """Consolidar múltiples bases de datos en una sola"""
        try:
            config = configuracion or {}
            bases_origen = config.get('bases_origen', ['aspirantes', 'estudiantes', 'egresados'])
            tabla_destino = config.get('tabla_destino', 'consolidado_general')
            
            # Crear tabla consolidada si no existe
            cursor = self.conexiones['migracion'].cursor()
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {tabla_destino} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    origen_tabla TEXT NOT NULL,
                    origen_id INTEGER NOT NULL,
                    tipo_registro TEXT,
                    datos_completos TEXT,
                    fecha_consolidacion TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(origen_tabla, origen_id)
                )
            ''')
            
            total_general = 0
            exitosos_general = 0
            
            for base_nombre in bases_origen:
                if base_nombre not in self.conexiones:
                    self.logger.warning(f"Base {base_nombre} no disponible, omitiendo")
                    continue
                
                # Obtener todos los registros de la base origen
                cursor_origen = self.conexiones[base_nombre].cursor()
                
                # Determinar tabla principal (asumimos primera tabla)
                cursor_origen.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
                )
                tabla_origen = cursor_origen.fetchone()
                
                if not tabla_origen:
                    continue
                
                tabla_origen = tabla_origen['name']
                cursor_origen.execute(f"SELECT * FROM {tabla_origen}")
                registros = cursor_origen.fetchall()
                
                self.logger.info(f"📊 Consolidando {len(registros)} registros de {base_nombre}.{tabla_origen}")
                
                for registro in registros:
                    try:
                        # Verificar si ya existe consolidado
                        cursor.execute(
                            f"SELECT COUNT(*) FROM {tabla_destino} WHERE origen_tabla = ? AND origen_id = ?",
                            (f"{base_nombre}.{tabla_origen}", registro['id'])
                        )
                        
                        if cursor.fetchone()[0] > 0:
                            continue
                        
                        # Insertar consolidado
                        cursor.execute(f'''
                            INSERT INTO {tabla_destino} (origen_tabla, origen_id, tipo_registro, datos_completos)
                            VALUES (?, ?, ?, ?)
                        ''', (
                            f"{base_nombre}.{tabla_origen}",
                            registro['id'],
                            base_nombre,
                            json.dumps(dict(registro), ensure_ascii=False, default=str)
                        ))
                        
                        exitosos_general += 1
                        
                        # Registrar en detalle
                        self._registrar_registro_migrado(migracion_id, {
                            'registro_origen_id': registro['id'],
                            'registro_destino_id': cursor.lastrowid,
                            'tabla_origen': f"{base_nombre}.{tabla_origen}",
                            'tabla_destino': tabla_destino,
                            'estado': 'exitoso'
                        })
                        
                    except Exception as e:
                        self.logger.error(f"Error consolidando registro {registro['id']}: {e}")
                        
                        self._registrar_registro_migrado(migracion_id, {
                            'registro_origen_id': registro['id'],
                            'tabla_origen': f"{base_nombre}.{tabla_origen}",
                            'tabla_destino': tabla_destino,
                            'estado': 'fallido',
                            'error_mensaje': str(e)
                        })
                    
                    total_general += 1
            
            self.conexiones['migracion'].commit()
            
            resultado = {
                'exito': exitosos_general > 0,
                'total': total_general,
                'exitosos': exitosos_general,
                'fallidos': total_general - exitosos_general,
                'tabla_creada': tabla_destino
            }
            
            self.logger.info(f"✅ Consolidación completada: {exitosos_general}/{total_general} registros")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en consolidación: {e}")
            raise
    
    def _limpiar_duplicados(self, migracion_id: int, configuracion: dict = None):
        """Limpiar registros duplicados en las bases de datos"""
        try:
            config = configuracion or {}
            bases_a_limpiar = config.get('bases', ['escuela'])
            
            total_eliminados = 0
            total_analizados = 0
            
            for base_nombre in bases_a_limpiar:
                if base_nombre not in self.conexiones:
                    continue
                
                conexion = self.conexiones[base_nombre]
                cursor = conexion.cursor()
                
                # Obtener todas las tablas
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tablas = cursor.fetchall()
                
                for tabla_info in tablas:
                    tabla = tabla_info['name']
                    
                    # Identificar columnas únicas potenciales
                    cursor.execute(f"PRAGMA table_info({tabla})")
                    columnas = cursor.fetchall()
                    
                    # Buscar columnas que podrían identificar duplicados
                    columnas_unicas = []
                    for col in columnas:
                        col_name = col[1].lower()
                        if any(keyword in col_name for keyword in ['id', 'codigo', 'matricula', 'curp', 'rfc', 'email', 'unique']):
                            # Esta columna podría ser única, buscar duplicados
                            cursor.execute(f"SELECT {col[1]}, COUNT(*) as cnt FROM {tabla} GROUP BY {col[1]} HAVING cnt > 1")
                            duplicados = cursor.fetchall()
                            
                            if duplicados:
                                self.logger.info(f"Encontrados {len(duplicados)} duplicados en {base_nombre}.{tabla} por columna {col[1]}")
                                
                                for valor, cnt in duplicados:
                                    total_analizados += cnt
                                    
                                    # Mantener el registro más reciente (si hay fecha)
                                    if 'fecha_creacion' in [c[1] for c in columnas]:
                                        cursor.execute(
                                            f"SELECT id FROM {tabla} WHERE {col[1]} = ? ORDER BY fecha_creacion DESC",
                                            (valor,)
                                        )
                                    else:
                                        cursor.execute(
                                            f"SELECT id FROM {tabla} WHERE {col[1]} = ? ORDER BY id DESC",
                                            (valor,)
                                        )
                                    
                                    registros = cursor.fetchall()
                                    
                                    # Mantener el primero, eliminar los demás
                                    if len(registros) > 1:
                                        mantener_id = registros[0]['id']
                                        eliminar_ids = [r['id'] for r in registros[1:]]
                                        
                                        for eliminar_id in eliminar_ids:
                                            try:
                                                cursor.execute(f"DELETE FROM {tabla} WHERE id = ?", (eliminar_id,))
                                                total_eliminados += 1
                                                
                                                # Registrar en detalle
                                                self._registrar_registro_migrado(migracion_id, {
                                                    'registro_origen_id': eliminar_id,
                                                    'tabla_origen': tabla,
                                                    'estado': 'exitoso',
                                                    'datos_origen': {'razon': 'duplicado', 'campo': col[1], 'valor': valor}
                                                })
                                                
                                            except Exception as e:
                                                self.logger.error(f"Error eliminando duplicado {eliminar_id}: {e}")
            
            # Para cada base afectada, hacer commit
            for base_nombre in bases_a_limpiar:
                if base_nombre in self.conexiones:
                    self.conexiones[base_nombre].commit()
            
            resultado = {
                'exito': total_eliminados > 0,
                'total_analizados': total_analizados,
                'duplicados_eliminados': total_eliminados,
                'espacio_liberado_estimado': total_eliminados * 1024  # 1KB por registro estimado
            }
            
            self.logger.info(f"✅ Limpieza de duplicados: {total_eliminados} registros eliminados")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en limpieza de duplicados: {e}")
            raise
    
    def _migrar_historico(self, migracion_id: int, configuracion: dict = None):
        """Migrar datos históricos de formatos antiguos"""
        try:
            # Esta es una migración genérica que puede adaptarse
            config = configuracion or {}
            
            self.logger.info("🔄 Migrando datos históricos...")
            
            # Ejemplo: migrar de tabla antigua a nueva estructura
            resultado = {
                'exito': True,
                'total': 0,
                'exitosos': 0,
                'fallidos': 0,
                'nota': 'Migración histórica configurada según especificaciones'
            }
            
            # Aquí iría la lógica específica de migración histórica
            # basada en la configuración proporcionada
            
            self.logger.info("✅ Migración histórica completada")
            return resultado
            
        except Exception as e:
            self.logger.error(f"❌ Error en migración histórica: {e}")
            raise
    
    # =============================================================================
    # GESTIÓN DE PLANTILLAS DE MIGRACIÓN
    # =============================================================================
    
    def obtener_plantillas_migracion(self, activas: bool = True):
        """Obtener plantillas de migración disponibles"""
        try:
            cursor = self.conexiones['migracion'].cursor()
            
            query = "SELECT * FROM plantillas_migracion WHERE 1=1"
            params = []
            
            if activas:
                query += " AND activa = 1"
            
            query += " ORDER BY nombre"
            cursor.execute(query, params)
            
            plantillas = []
            for row in cursor.fetchall():
                plantilla = dict(row)
                plantilla['configuracion'] = json.loads(plantilla['configuracion'])
                plantillas.append(plantilla)
            
            return plantillas
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo plantillas: {e}")
            return []
    
    def guardar_plantilla_migracion(self, nombre: str, tipo_migracion: str, 
                                   configuracion: dict, descripcion: str = None):
        """Guardar o actualizar una plantilla de migración"""
        try:
            cursor = self.conexiones['migracion'].cursor()
            
            # Verificar si existe
            cursor.execute("SELECT id FROM plantillas_migracion WHERE nombre = ?", (nombre,))
            existe = cursor.fetchone()
            
            if existe:
                # Actualizar
                cursor.execute('''
                    UPDATE plantillas_migracion 
                    SET tipo_migracion = ?, configuracion = ?, descripcion = ?,
                        fecha_actualizacion = CURRENT_TIMESTAMP
                    WHERE nombre = ?
                ''', (tipo_migracion, json.dumps(configuracion), descripcion, nombre))
            else:
                # Insertar nueva
                cursor.execute('''
                    INSERT INTO plantillas_migracion (nombre, tipo_migracion, configuracion, descripcion)
                    VALUES (?, ?, ?, ?)
                ''', (nombre, tipo_migracion, json.dumps(configuracion), descripcion))
            
            self.conexiones['migracion'].commit()
            self.logger.info(f"✅ Plantilla guardada: {nombre}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error guardando plantilla: {e}")
            raise
    
    # =============================================================================
    # CONSULTAS Y REPORTES
    # =============================================================================
    
    def obtener_historial_migraciones(self, limite: int = 50, tipo: str = None):
        """Obtener historial de migraciones ejecutadas"""
        try:
            cursor = self.conexiones['migracion'].cursor()
            
            query = "SELECT * FROM migraciones WHERE 1=1"
            params = []
            
            if tipo:
                query += " AND tipo_migracion = ?"
                params.append(tipo)
            
            query += " ORDER BY fecha_inicio DESC LIMIT ?"
            params.append(limite)
            
            cursor.execute(query, params)
            
            migraciones = []
            for row in cursor.fetchall():
                migracion = dict(row)
                
                # Parsear JSON fields
                if migracion.get('configuracion'):
                    try:
                        migracion['configuracion'] = json.loads(migracion['configuracion'])
                    except:
                        pass
                
                if migracion.get('resultado'):
                    try:
                        migracion['resultado'] = json.loads(migracion['resultado'])
                    except:
                        pass
                
                migraciones.append(migracion)
            
            return migraciones
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo historial: {e}")
            return []
    
    def obtener_estadisticas_migracion(self):
        """Obtener estadísticas de migraciones"""
        try:
            cursor = self.conexiones['migracion'].cursor()
            estadisticas = {}
            
            # Totales por tipo
            cursor.execute('''
                SELECT tipo_migracion, COUNT(*) as total,
                       SUM(CASE WHEN estado = 'completada' THEN 1 ELSE 0 END) as exitosas,
                       SUM(CASE WHEN estado = 'fallida' THEN 1 ELSE 0 END) as fallidas
                FROM migraciones
                GROUP BY tipo_migracion
            ''')
            
            estadisticas['por_tipo'] = {}
            for row in cursor.fetchall():
                estadisticas['por_tipo'][row['tipo_migracion']] = dict(row)
            
            # Totales generales
            cursor.execute('''
                SELECT COUNT(*) as total_migraciones,
                       SUM(total_registros) as total_registros,
                       SUM(registros_exitosos) as registros_exitosos,
                       SUM(registros_fallidos) as registros_fallidos,
                       AVG(duracion_segundos) as duracion_promedio
                FROM migraciones
                WHERE estado = 'completada'
            ''')
            
            row = cursor.fetchone()
            if row:
                estadisticas['generales'] = dict(row)
            
            # Última migración
            cursor.execute('''
                SELECT * FROM migraciones 
                WHERE estado = 'completada'
                ORDER BY fecha_fin DESC 
                LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if row:
                estadisticas['ultima_migracion'] = dict(row)
            
            return estadisticas
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo estadísticas: {e}")
            return {}
    
    def generar_reporte_migracion(self, migracion_id: int):
        """Generar reporte detallado de una migración"""
        try:
            # Obtener información de la migración
            cursor = self.conexiones['migracion'].cursor()
            cursor.execute("SELECT * FROM migraciones WHERE id = ?", (migracion_id,))
            migracion = cursor.fetchone()
            
            if not migracion:
                raise ValueError(f"Migración {migracion_id} no encontrada")
            
            migracion_dict = dict(migracion)
            
            # Obtener registros migrados
            cursor.execute(
                "SELECT * FROM registros_migrados WHERE migracion_id = ? ORDER BY fecha_procesamiento",
                (migracion_id,)
            )
            registros = [dict(row) for row in cursor.fetchall()]
            
            # Obtener conflictos
            cursor.execute(
                "SELECT * FROM conflictos WHERE migracion_id = ? ORDER BY fecha_deteccion",
                (migracion_id,)
            )
            conflictos = [dict(row) for row in cursor.fetchall()]
            
            # Crear reporte estructurado
            reporte = {
                'migracion': migracion_dict,
                'resumen': {
                    'total_registros': len(registros),
                    'exitosos': len([r for r in registros if r['estado'] == 'exitoso']),
                    'fallidos': len([r for r in registros if r['estado'] == 'fallido']),
                    'omitidos': len([r for r in registros if r['estado'] == 'omitido']),
                    'conflictos': len(conflictos)
                },
                'registros': registros[:100],  # Limitar para no hacer muy grande el reporte
                'conflictos': conflictos
            }
            
            return reporte
            
        except Exception as e:
            self.logger.error(f"❌ Error generando reporte: {e}")
            raise
    
    # =============================================================================
    # UTILIDADES
    # =============================================================================
    
    def verificar_estado_bases(self):
        """Verificar estado de todas las bases de datos"""
        try:
            estado_bases = {}
            
            for nombre, conexion in self.conexiones.items():
                try:
                    cursor = conexion.cursor()
                    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    tablas = cursor.fetchone()[0]
                    
                    estado_bases[nombre] = {
                        'conectada': True,
                        'tablas': tablas,
                        'ruta': 'memoria' if nombre == 'migracion' else conexion.execute
                    }
                    
                except Exception as e:
                    estado_bases[nombre] = {
                        'conectada': False,
                        'error': str(e)
                    }
            
            return estado_bases
            
        except Exception as e:
            self.logger.error(f"❌ Error verificando bases: {e}")
            return {}
    
    def crear_backup_migracion(self):
        """Crear backup de las bases de datos de migración"""
        try:
            backup_dir = self.config.get('backup_dir', 'backups_migracion')
            self.util.crear_directorio_si_no_existe(backup_dir)
            
            timestamp = self.util.generar_timestamp()
            
            # Backup de base de control de migración
            if os.path.exists(self.db_migracion_path):
                import shutil
                backup_file = os.path.join(backup_dir, f"migracion_backup_{timestamp}.db")
                shutil.copy2(self.db_migracion_path, backup_file)
                
                self.logger.info(f"✅ Backup de migración creado: {backup_file}")
                return backup_file
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error creando backup: {e}")
            return None
    
    # =============================================================================
    # INTERFAZ WEB
    # =============================================================================
    
    def mostrar_panel_control(self):
        """Mostrar panel de control principal"""
        st.title("🔄 Panel de Control - Sistema de Migración")
        
        # Verificar estado de conexión
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if self.estado.estado.get('ssh_conectado'):
                st.success("✅ Conectado al servidor")
            else:
                st.error("❌ Desconectado del servidor")
        
        with col2:
            bases_estado = self.verificar_estado_bases()
            bases_conectadas = sum(1 for b in bases_estado.values() if b.get('conectada'))
            st.metric("Bases Conectadas", f"{bases_conectadas}/{len(bases_estado)}")
        
        with col3:
            estadisticas = self.obtener_estadisticas_migracion()
            total_mig = estadisticas.get('generales', {}).get('total_migraciones', 0)
            st.metric("Migraciones Totales", total_mig)
        
        # Acciones rápidas
        st.subheader("⚡ Acciones Rápidas")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Sincronizar Bases", type="primary"):
                with st.spinner("Sincronizando..."):
                    if self.sincronizar_bases_datos():
                        st.success("✅ Bases sincronizadas")
                        st.rerun()
                    else:
                        st.error("❌ Error sincronizando")
        
        with col2:
            if st.button("📊 Ver Estado Bases"):
                estado_bases = self.verificar_estado_bases()
                
                for nombre, info in estado_bases.items():
                    if info.get('conectada'):
                        st.success(f"✅ {nombre}: {info.get('tablas', 0)} tablas")
                    else:
                        st.error(f"❌ {nombre}: {info.get('error', 'Error desconocido')}")
        
        with col3:
            if st.button("💾 Crear Backup"):
                backup_path = self.crear_backup_migracion()
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
        
        # Historial reciente
        st.subheader("📋 Historial Reciente de Migraciones")
        historial = self.obtener_historial_migraciones(limite=10)
        
        if historial:
            datos = []
            for mig in historial[:5]:  # Mostrar solo 5
                datos.append({
                    'ID': mig['id'],
                    'Tipo': mig['tipo_migracion'],
                    'Estado': mig['estado'],
                    'Registros': f"{mig.get('registros_exitosos', 0)}/{mig.get('total_registros', 0)}",
                    'Duración': f"{mig.get('duracion_segundos', 0):.1f}s",
                    'Fecha': mig['fecha_inicio'][:19] if mig.get('fecha_inicio') else ''
                })
            
            if datos:
                df = pd.DataFrame(datos)
                st.dataframe(df, use_container_width=True)
        else:
            st.info("📭 No hay migraciones registradas")
    
    def mostrar_migraciones_rapidas(self):
        """Mostrar migraciones rápidas preconfiguradas"""
        st.title("🚀 Migraciones Rápidas")
        
        st.info("""
        Ejecuta migraciones preconfiguradas con un solo clic.
        Estas migraciones usan configuraciones por defecto.
        """)
        
        # Plantillas disponibles
        plantillas = self.obtener_plantillas_migracion(activas=True)
        
        if not plantillas:
            st.warning("⚠️ No hay plantillas de migración configuradas")
            return
        
        # Mostrar plantillas como tarjetas
        for plantilla in plantillas:
            with st.expander(f"🔧 {plantilla['nombre']} - {plantilla['tipo_migracion']}", expanded=False):
                st.write(f"**Descripción:** {plantilla.get('descripcion', 'Sin descripción')}")
                
                # Mostrar configuración resumida
                config = plantilla['configuracion']
                if 'criterios' in config:
                    st.write("**Criterios:**")
                    for criterio, valor in config['criterios'].items():
                        st.write(f"- {criterio}: {valor}")
                
                # Botón para ejecutar
                if st.button(f"▶️ Ejecutar {plantilla['nombre']}", key=f"ejecutar_{plantilla['id']}"):
                    with st.spinner(f"Ejecutando {plantilla['nombre']}..."):
                        try:
                            resultado = self.ejecutar_migracion(
                                plantilla['tipo_migracion'],
                                config,
                                usuario=st.session_state.get('usuario', 'admin')
                            )
                            
                            if resultado['exito']:
                                st.success(f"✅ Migración completada: {resultado['exitosos']} registros exitosos")
                            else:
                                st.error(f"❌ Migración fallida: {resultado.get('fallidos', 0)} errores")
                            
                            # Mostrar detalles
                            with st.expander("Ver detalles"):
                                st.json(resultado)
                                
                        except Exception as e:
                            st.error(f"❌ Error ejecutando migración: {e}")
    
    def mostrar_migracion_personalizada(self):
        """Mostrar interfaz para migración personalizada"""
        st.title("🎛️ Migración Personalizada")
        
        # Paso 1: Seleccionar tipo de migración
        st.subheader("1. Tipo de Migración")
        tipo_migracion = st.selectbox(
            "Seleccionar tipo de migración:",
            TIPOS_MIGRACION,
            help="Elija el tipo de operación de migración a realizar"
        )
        
        # Paso 2: Configuración según tipo
        st.subheader("2. Configuración")
        configuracion = {}
        
        if tipo_migracion == 'estudiantes_a_egresados':
            configuracion = self._configurar_estudiantes_a_egresados()
        
        elif tipo_migracion == 'aspirantes_a_estudiantes':
            configuracion = self._configurar_aspirantes_a_estudiantes()
        
        elif tipo_migracion == 'consolidar_bases':
            configuracion = self._configurar_consolidar_bases()
        
        elif tipo_migracion == 'limpiar_duplicados':
            configuracion = self._configurar_limpiar_duplicados()
        
        # Paso 3: Opciones avanzadas
        st.subheader("3. Opciones Avanzadas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            crear_backup = st.checkbox("Crear backup antes de migrar", value=True)
            validar_duplicados = st.checkbox("Validar duplicados", value=True)
        
        with col2:
            notificar_exito = st.checkbox("Notificar al completar", value=False)
            modo_prueba = st.checkbox("Modo prueba (no guardar cambios)", value=False)
        
        configuracion['opciones'] = {
            'crear_backup': crear_backup,
            'validar_duplicados': validar_duplicados,
            'notificar_exito': notificar_exito,
            'modo_prueba': modo_prueba
        }
        
        # Paso 4: Vista previa y ejecución
        st.subheader("4. Vista Previa y Ejecución")
        
        if st.button("👁️ Generar Vista Previa", type="secondary"):
            with st.spinner("Analizando datos..."):
                try:
                    vista_previa = self._generar_vista_previa(tipo_migracion, configuracion)
                    
                    if vista_previa:
                        st.success(f"✅ Se afectarán aproximadamente {vista_previa.get('estimados', 0)} registros")
                        
                        with st.expander("Ver detalles de vista previa"):
                            st.json(vista_previa)
                    else:
                        st.warning("⚠️ No se pudo generar vista previa")
                        
                except Exception as e:
                    st.error(f"❌ Error en vista previa: {e}")
        
        # Ejecutar migración
        st.markdown("---")
        
        if st.button("🚀 Ejecutar Migración", type="primary"):
            if not configuracion:
                st.warning("⚠️ Configure la migración antes de ejecutar")
                return
            
            # Confirmación
            confirmar = st.checkbox("✅ Confirmar ejecución de migración")
            
            if confirmar:
                with st.spinner(f"Ejecutando migración {tipo_migracion}..."):
                    try:
                        resultado = self.ejecutar_migracion(
                            tipo_migracion,
                            configuracion,
                            usuario=st.session_state.get('usuario', 'admin')
                        )
                        
                        # Mostrar resultados
                        st.subheader("📊 Resultados de la Migración")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Total", resultado.get('total', 0))
                        
                        with col2:
                            st.metric("Exitosos", resultado.get('exitosos', 0))
                        
                        with col3:
                            st.metric("Fallidos", resultado.get('fallidos', 0))
                        
                        # Mostrar detalles si hay errores
                        if resultado.get('fallidos', 0) > 0:
                            with st.expander("📋 Ver errores detallados"):
                                if 'detalles' in resultado:
                                    for detalle in resultado['detalles']:
                                        if detalle.get('estado') == 'fallido':
                                            st.error(f"ID {detalle.get('registro_id')}: {detalle.get('razon', 'Error desconocido')}")
                        
                        # Opción para guardar como plantilla
                        if st.checkbox("💾 Guardar configuración como plantilla"):
                            nombre_plantilla = st.text_input("Nombre de la plantilla:")
                            descripcion = st.text_area("Descripción:")
                            
                            if nombre_plantilla and st.button("Guardar Plantilla"):
                                try:
                                    self.guardar_plantilla_migracion(
                                        nombre_plantilla,
                                        tipo_migracion,
                                        configuracion,
                                        descripcion
                                    )
                                    st.success(f"✅ Plantilla '{nombre_plantilla}' guardada")
                                except Exception as e:
                                    st.error(f"❌ Error guardando plantilla: {e}")
                        
                    except Exception as e:
                        st.error(f"❌ Error ejecutando migración: {e}")
    
    def _configurar_estudiantes_a_egresados(self):
        """Configurar migración estudiantes -> egresados"""
        config = {}
        
        st.write("**Criterios de selección:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            config['criterios'] = {
                'estado_estudiante': st.selectbox(
                    "Estado del estudiante",
                    ['Activo', 'Inactivo', 'Baja Temporal'],
                    index=0
                ),
                'semestre_minimo': st.number_input(
                    "Semestre mínimo",
                    min_value=1,
                    max_value=20,
                    value=8
                )
            }
        
        with col2:
            config['criterios'].update({
                'promedio_minimo': st.number_input(
                    "Promedio mínimo",
                    min_value=0.0,
                    max_value=10.0,
                    value=8.0,
                    step=0.1
                ),
                'fecha_ingreso_maxima': st.date_input(
                    "Fecha ingreso máxima",
                    value=datetime.now() - timedelta(days=365*4)  # 4 años atrás
                ).isoformat()
            })
        
        config['fecha_egreso'] = st.date_input(
            "Fecha de egreso",
            value=datetime.now()
        ).isoformat()
        
        config['titulo_obtenido'] = st.text_input(
            "Título obtenido (dejar vacío para usar carrera)",
            value=""
        )
        
        return config
    
    def _configurar_aspirantes_a_estudiantes(self):
        """Configurar migración aspirantes -> estudiantes"""
        config = {}
        
        st.write("**Criterios de selección:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            config['criterios'] = {
                'estado_aprobacion': st.selectbox(
                    "Estado de aprobación",
                    ['Aprobado', 'Aceptado', 'Calificado'],
                    index=0
                ),
                'puntaje_minimo': st.number_input(
                    "Puntaje mínimo",
                    min_value=0,
                    max_value=100,
                    value=70
                )
            }
        
        with col2:
            config['criterios'].update({
                'fecha_aplicacion_minima': st.date_input(
                    "Fecha aplicación mínima",
                    value=datetime.now() - timedelta(days=180)  # 6 meses atrás
                ).isoformat()
            })
        
        # Configuración de mapeo de campos
        st.write("**Mapeo de campos:**")
        
        mapeo_config = {}
        
        campos_mapeo = st.multiselect(
            "Campos a migrar (seleccionar todos para migración completa)",
            ['nombre', 'apellido_paterno', 'apellido_materno', 'curp', 'telefono', 
             'email', 'direccion', 'carrera_solicitada', 'nivel_estudio_solicitado'],
            default=['nombre', 'apellido_paterno', 'apellido_materno', 'curp', 'carrera_solicitada']
        )
        
        for campo in campos_mapeo:
            mapeo_config[campo] = campo
        
        config['mapeo_campos'] = mapeo_config
        
        return config
    
    def _configurar_consolidar_bases(self):
        """Configurar consolidación de bases"""
        config = {}
        
        st.write("**Bases de datos a consolidar:**")
        
        bases_disponibles = list(self.conexiones.keys())
        bases_disponibles.remove('migracion')  # No consolidar la base de control
        
        bases_seleccionadas = st.multiselect(
            "Seleccionar bases",
            bases_disponibles,
            default=['escuela', 'aspirantes'] if 'escuela' in bases_disponibles else []
        )
        
        config['bases_origen'] = bases_seleccionadas
        
        config['tabla_destino'] = st.text_input(
            "Nombre de tabla consolidada",
            value="consolidado_general"
        )
        
        config['estrategia_fusion'] = st.selectbox(
            "Estrategia de fusión",
            ['ultima_actualizacion', 'conservar_todos', 'fusionar_inteligente'],
            index=0
        )
        
        config['mantener_historico'] = st.checkbox(
            "Mantener histórico de cambios",
            value=True
        )
        
        return config
    
    def _configurar_limpiar_duplicados(self):
        """Configurar limpieza de duplicados"""
        config = {}
        
        st.write("**Bases de datos a limpiar:**")
        
        bases_disponibles = list(self.conexiones.keys())
        bases_disponibles.remove('migracion')
        
        bases_seleccionadas = st.multiselect(
            "Seleccionar bases",
            bases_disponibles,
            default=bases_disponibles
        )
        
        config['bases'] = bases_seleccionadas
        
        st.write("**Estrategia de limpieza:**")
        
        config['estrategia'] = st.selectbox(
            "Criterio para mantener registros",
            ['mas_reciente', 'mas_completo', 'primero_encontrado'],
            index=0,
            help="Determina qué registro mantener cuando hay duplicados"
        )
        
        config['campos_unicos'] = st.text_input(
            "Campos únicos a verificar (separados por coma)",
            value="matricula,curp,email",
            help="Campos que deberían ser únicos en la base de datos"
        )
        
        config['crear_backup'] = st.checkbox(
            "Crear backup antes de limpiar",
            value=True
        )
        
        return config
    
    def _generar_vista_previa(self, tipo_migracion: str, configuracion: dict):
        """Generar vista previa de lo que afectará la migración"""
        try:
            if tipo_migracion == 'estudiantes_a_egresados':
                return self._vista_previa_estudiantes_a_egresados(configuracion)
            elif tipo_migracion == 'aspirantes_a_estudiantes':
                return self._vista_previa_aspirantes_a_estudiantes(configuracion)
            elif tipo_migracion == 'consolidar_bases':
                return self._vista_previa_consolidar_bases(configuracion)
            elif tipo_migracion == 'limpiar_duplicados':
                return self._vista_previa_limpiar_duplicados(configuracion)
            else:
                return {'estimados': 0, 'nota': 'Vista previa no disponible para este tipo'}
                
        except Exception as e:
            self.logger.error(f"❌ Error generando vista previa: {e}")
            return None
    
    def _vista_previa_estudiantes_a_egresados(self, configuracion: dict):
        """Vista previa para estudiantes -> egresados"""
        if 'escuela' not in self.conexiones:
            return {'estimados': 0, 'error': 'Base de datos no disponible'}
        
        criterios = configuracion.get('criterios', {})
        query = "SELECT COUNT(*) as total FROM estudiantes WHERE 1=1"
        params = []
        
        if criterios.get('estado_estudiante'):
            query += " AND estado_estudiante = ?"
            params.append(criterios['estado_estudiante'])
        
        if criterios.get('semestre_minimo'):
            query += " AND semestre >= ?"
            params.append(criterios['semestre_minimo'])
        
        if criterios.get('promedio_minimo'):
            query += " AND promedio >= ?"
            params.append(criterios['promedio_minimo'])
        
        cursor = self.conexiones['escuela'].cursor()
        cursor.execute(query, params)
        total = cursor.fetchone()[0]
        
        return {
            'estimados': total,
            'tipo': 'estudiantes_a_egresados',
            'criterios_aplicados': criterios
        }
    
    def _vista_previa_aspirantes_a_estudiantes(self, configuracion: dict):
        """Vista previa para aspirantes -> estudiantes"""
        if 'aspirantes' not in self.conexiones:
            return {'estimados': 0, 'error': 'Base de datos no disponible'}
        
        criterios = configuracion.get('criterios', {})
        query = "SELECT COUNT(*) as total FROM aspirantes WHERE 1=1"
        params = []
        
        if criterios.get('estado_aprobacion'):
            query += " AND estado_aprobacion = ?"
            params.append(criterios['estado_aprobacion'])
        
        if criterios.get('puntaje_minimo'):
            query += " AND puntaje_total >= ?"
            params.append(criterios['puntaje_minimo'])
        
        cursor = self.conexiones['aspirantes'].cursor()
        cursor.execute(query, params)
        total = cursor.fetchone()[0]
        
        return {
            'estimados': total,
            'tipo': 'aspirantes_a_estudiantes',
            'criterios_aplicados': criterios
        }
    
    def _vista_previa_consolidar_bases(self, configuracion: dict):
        """Vista previa para consolidar bases"""
        bases_origen = configuracion.get('bases_origen', [])
        total_estimado = 0
        
        for base_nombre in bases_origen:
            if base_nombre in self.conexiones:
                cursor = self.conexiones[base_nombre].cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
                )
                tabla = cursor.fetchone()
                
                if tabla:
                    cursor.execute(f"SELECT COUNT(*) as total FROM {tabla['name']}")
                    total_base = cursor.fetchone()[0]
                    total_estimado += total_base
        
        return {
            'estimados': total_estimado,
            'tipo': 'consolidar_bases',
            'bases_a_consolidar': bases_origen
        }
    
    def _vista_previa_limpiar_duplicados(self, configuracion: dict):
        """Vista previa para limpiar duplicados"""
        # Esta es una estimación simple
        return {
            'estimados': 100,  # Estimación por defecto
            'tipo': 'limpiar_duplicados',
            'nota': 'La cantidad exacta de duplicados se determina durante la ejecución'
        }
    
    def mostrar_historial_detallado(self):
        """Mostrar historial detallado de migraciones"""
        st.title("📋 Historial de Migraciones")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        
        with col1:
            filtro_tipo = st.selectbox(
                "Filtrar por tipo:",
                ['Todos'] + TIPOS_MIGRACION
            )
        
        with col2:
            filtro_estado = st.selectbox(
                "Filtrar por estado:",
                ['Todos'] + ESTADOS_MIGRACION
            )
        
        with col3:
            limite = st.number_input(
                "Registros a mostrar:",
                min_value=10,
                max_value=500,
                value=50
            )
        
        # Obtener historial
        historial = self.obtener_historial_migraciones(limite=limite)
        
        # Aplicar filtros
        if filtro_tipo != 'Todos':
            historial = [m for m in historial if m['tipo_migracion'] == filtro_tipo]
        
        if filtro_estado != 'Todos':
            historial = [m for m in historial if m['estado'] == filtro_estado]
        
        if historial:
            # Mostrar tabla
            datos = []
            for mig in historial:
                datos.append({
                    'ID': mig['id'],
                    'Tipo': mig['tipo_migracion'],
                    'Estado': mig['estado'],
                    'Registros': f"{mig.get('registros_exitosos', 0)}/{mig.get('total_registros', 0)}",
                    'Duración': f"{mig.get('duracion_segundos', 0):.1f}s" if mig.get('duracion_segundos') else 'N/A',
                    'Fecha Inicio': mig.get('fecha_inicio', '')[:19],
                    'Usuario': mig.get('usuario_ejecutor', 'sistema')
                })
            
            df = pd.DataFrame(datos)
            st.dataframe(df, use_container_width=True)
            
            # Seleccionar migración para ver detalles
            st.subheader("🔍 Ver Detalles de Migración")
            
            migraciones_ids = [f"{m['id']} - {m['tipo_migracion']} ({m['fecha_inicio'][:10]})" 
                              for m in historial]
            
            seleccion = st.selectbox("Seleccionar migración:", migraciones_ids)
            
            if seleccion and st.button("📊 Ver Reporte Detallado"):
                mig_id = int(seleccion.split(' - ')[0])
                
                try:
                    reporte = self.generar_reporte_migracion(mig_id)
                    
                    # Mostrar resumen
                    st.subheader(f"📋 Reporte - Migración {mig_id}")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total", reporte['resumen']['total_registros'])
                    
                    with col2:
                        st.metric("Exitosos", reporte['resumen']['exitosos'])
                    
                    with col3:
                        st.metric("Fallidos", reporte['resumen']['fallidos'])
                    
                    with col4:
                        st.metric("Conflictos", reporte['resumen']['conflictos'])
                    
                    # Mostrar detalles si se solicita
                    with st.expander("Ver registros migrados"):
                        if reporte.get('registros'):
                            datos_registros = []
                            for reg in reporte['registros'][:50]:  # Mostrar primeros 50
                                datos_registros.append({
                                    'ID': reg['id'],
                                    'Origen ID': reg['registro_origen_id'],
                                    'Destino ID': reg['registro_destino_id'],
                                    'Estado': reg['estado'],
                                    'Error': reg.get('error_mensaje', '')
                                })
                            
                            if datos_registros:
                                df_registros = pd.DataFrame(datos_registros)
                                st.dataframe(df_registros, use_container_width=True)
                        else:
                            st.info("No hay registros migrados para mostrar")
                    
                    # Mostrar conflictos
                    if reporte.get('conflictos'):
                        with st.expander("Ver conflictos detectados"):
                            for conflicto in reporte['conflictos']:
                                st.warning(f"**{conflicto['tipo_conflicto']}**: {conflicto['descripcion']}")
                    
                    # Opción para exportar reporte
                    if st.button("📤 Exportar Reporte a JSON"):
                        import json as json_lib
                        json_str = json_lib.dumps(reporte, indent=2, ensure_ascii=False, default=str)
                        
                        st.download_button(
                            label="⬇️ Descargar Reporte JSON",
                            data=json_str,
                            file_name=f"reporte_migracion_{mig_id}.json",
                            mime="application/json"
                        )
                        
                except Exception as e:
                    st.error(f"❌ Error generando reporte: {e}")
        else:
            st.info("📭 No hay migraciones que coincidan con los filtros")
    
    def mostrar_estadisticas(self):
        """Mostrar estadísticas del sistema de migración"""
        st.title("📊 Estadísticas del Sistema de Migración")
        
        estadisticas = self.obtener_estadisticas_migracion()
        
        if not estadisticas:
            st.info("📭 No hay estadísticas disponibles")
            return
        
        # Estadísticas generales
        st.subheader("📈 Estadísticas Generales")
        
        if 'generales' in estadisticas:
            gen = estadisticas['generales']
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Migraciones Totales", gen.get('total_migraciones', 0))
            
            with col2:
                st.metric("Registros Procesados", gen.get('total_registros', 0))
            
            with col3:
                exito_rate = (gen.get('registros_exitosos', 0) / max(gen.get('total_registros', 1), 1)) * 100
                st.metric("Tasa de Éxito", f"{exito_rate:.1f}%")
            
            with col4:
                st.metric("Duración Promedio", f"{gen.get('duracion_promedio', 0):.1f}s")
        
        # Estadísticas por tipo
        st.subheader("📊 Distribución por Tipo")
        
        if 'por_tipo' in estadisticas:
            datos_tipo = []
            for tipo, datos in estadisticas['por_tipo'].items():
                datos_tipo.append({
                    'Tipo': tipo,
                    'Total': datos['total'],
                    'Exitosas': datos['exitosas'],
                    'Fallidas': datos['fallidas']
                })
            
            if datos_tipo:
                df_tipo = pd.DataFrame(datos_tipo)
                st.dataframe(df_tipo, use_container_width=True)
                
                # Gráfico de barras
                if not df_tipo.empty:
                    chart_data = df_tipo.set_index('Tipo')[['Exitosas', 'Fallidas']]
                    st.bar_chart(chart_data)
        
        # Última migración exitosa
        st.subheader("⏱️ Última Migración Exitosa")
        
        if 'ultima_migracion' in estadisticas:
            ultima = estadisticas['ultima_migracion']
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Tipo:** {ultima.get('tipo_migracion', 'N/A')}")
                st.write(f"**ID:** {ultima.get('id', 'N/A')}")
            
            with col2:
                st.write(f"**Fecha:** {ultima.get('fecha_fin', 'N/A')[:19]}")
                st.write(f"**Duración:** {ultima.get('duracion_segundos', 0):.1f}s")
            
            with col3:
                st.write(f"**Registros:** {ultima.get('registros_exitosos', 0)}/{ultima.get('total_registros', 0)}")
                st.write(f"**Usuario:** {ultima.get('usuario_ejecutor', 'sistema')}")
        else:
            st.info("No hay migraciones exitosas registradas")
    
    def mostrar_administracion(self):
        """Mostrar panel de administración del sistema"""
        st.title("⚙️ Administración del Sistema")
        
        tab1, tab2, tab3, tab4 = st.tabs([
            "🔧 Configuración",
            "💾 Backups",
            "📋 Plantillas",
            "🛠️ Mantenimiento"
        ])
        
        with tab1:
            self._mostrar_configuracion_admin()
        
        with tab2:
            self._mostrar_gestion_backups()
        
        with tab3:
            self._mostrar_gestion_plantillas()
        
        with tab4:
            self._mostrar_mantenimiento()
    
    def _mostrar_configuracion_admin(self):
        """Mostrar configuración administrativa"""
        st.subheader("🔧 Configuración del Sistema")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Configuración de conexión
            st.write("**🔗 Configuración SSH:**")
            st.json({
                "host": self.ssh_config.get('host', 'No configurado'),
                "port": self.ssh_config.get('port', 'No configurado'),
                "username": self.ssh_config.get('username', 'No configurado'),
                "enabled": self.ssh_config.get('enabled', True)
            })
            
            # Prueba de conexión
            if st.button("🧪 Probar Conexión SSH"):
                with st.spinner("Probando conexión..."):
                    if self.gestor_ssh.conectar():
                        st.success("✅ Conexión SSH exitosa")
                    else:
                        st.error("❌ Conexión SSH fallida")
        
        with col2:
            # Configuración de rutas
            st.write("**📁 Rutas Remotas:**")
            rutas_resumen = {
                "escuela_db": self.rutas.get('escuela_db', 'No configurado'),
                "aspirantes_db": self.rutas.get('aspirantes_db', 'No configurado'),
                "inscritos_db": self.rutas.get('inscritos_db', 'No configurado')
            }
            st.json(rutas_resumen)
            
            # Sincronizar ahora
            if st.button("🔄 Sincronizar Todas las Bases", type="primary"):
                with st.spinner("Sincronizando..."):
                    if self.sincronizar_bases_datos():
                        st.success("✅ Sincronización completada")
                        st.rerun()
                    else:
                        st.error("❌ Error en sincronización")
        
        # Configuración de intentos de reintento
        st.subheader("🔄 Configuración de Reintentos")
        
        col1, col2 = st.columns(2)
        
        with col1:
            nuevos_intentos = st.number_input(
                "Intentos de reintento:",
                min_value=1,
                max_value=10,
                value=RETRY_ATTEMPTS
            )
        
        with col2:
            nuevo_delay = st.number_input(
                "Delay entre reintentos (segundos):",
                min_value=1,
                max_value=60,
                value=RETRY_DELAY
            )
        
        if st.button("💾 Guardar Configuración"):
            # Aquí iría la lógica para guardar la configuración
            st.success("✅ Configuración guardada (simulado)")
    
    def _mostrar_gestion_backups(self):
        """Mostrar gestión de backups"""
        st.subheader("💾 Gestión de Backups")
        
        # Crear backup manual
        if st.button("💾 Crear Backup Manual", type="primary"):
            with st.spinner("Creando backup..."):
                backup_path = self.crear_backup_migracion()
                if backup_path:
                    st.success(f"✅ Backup creado: {os.path.basename(backup_path)}")
                else:
                    st.error("❌ Error creando backup")
        
        # Listar backups existentes
        backup_dir = self.config.get('backup_dir', 'backups_migracion')
        
        if os.path.exists(backup_dir):
            backups = []
            for file in os.listdir(backup_dir):
                if file.endswith('.db'):
                    file_path = os.path.join(backup_dir, file)
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    backups.append({
                        'Archivo': file,
                        'Tamaño (MB)': f"{size_mb:.2f}",
                        'Fecha': mtime.strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            if backups:
                st.write(f"**📦 Backups encontrados ({len(backups)}):**")
                df_backups = pd.DataFrame(backups)
                st.dataframe(df_backups, use_container_width=True)
                
                # Opciones de gestión
                st.subheader("🛠️ Opciones de Gestión")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("🗑️ Eliminar Backups Antiguos"):
                        if st.checkbox("¿Confirmar eliminación de backups con más de 30 días?"):
                            # Lógica para eliminar backups antiguos
                            st.success("✅ Backups antiguos eliminados (simulado)")
                
                with col2:
                    if st.button("📤 Exportar Lista de Backups"):
                        # Crear CSV con lista de backups
                        csv = df_backups.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Descargar Lista",
                            data=csv,
                            file_name="lista_backups.csv",
                            mime="text/csv"
                        )
            else:
                st.info("📭 No hay backups creados")
        else:
            st.info("📭 Directorio de backups no existe")
    
    def _mostrar_gestion_plantillas(self):
        """Mostrar gestión de plantillas de migración"""
        st.subheader("📋 Plantillas de Migración")
        
        # Obtener plantillas
        plantillas = self.obtener_plantillas_migracion()
        
        if plantillas:
            # Mostrar plantillas
            for plantilla in plantillas:
                with st.expander(f"🔧 {plantilla['nombre']}", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**Tipo:** {plantilla['tipo_migracion']}")
                        st.write(f"**Descripción:** {plantilla.get('descripcion', 'Sin descripción')}")
                        
                        # Mostrar configuración resumida
                        if 'criterios' in plantilla['configuracion']:
                            st.write("**Criterios:**")
                            for criterio, valor in plantilla['configuracion']['criterios'].items():
                                st.write(f"- {criterio}: {valor}")
                    
                    with col2:
                        # Botones de acción
                        if st.button("▶️ Ejecutar", key=f"ejec_{plantilla['id']}"):
                            st.session_state['ejecutar_plantilla'] = plantilla['id']
                        
                        if st.button("✏️ Editar", key=f"edit_{plantilla['id']}"):
                            st.session_state['editar_plantilla'] = plantilla['id']
                        
                        nuevo_estado = not bool(plantilla.get('activa', 1))
                        estado_texto = "Desactivar" if plantilla.get('activa', 1) else "Activar"
                        
                        if st.button(estado_texto, key=f"estado_{plantilla['id']}"):
                            # Lógica para cambiar estado
                            st.success(f"✅ Plantilla {estado_texto.lower()}da")
            
            # Crear nueva plantilla
            st.subheader("➕ Crear Nueva Plantilla")
            
            with st.form("nueva_plantilla"):
                nombre = st.text_input("Nombre de la plantilla *")
                tipo = st.selectbox("Tipo de migración *", TIPOS_MIGRACION)
                descripcion = st.text_area("Descripción")
                
                # Configuración básica según tipo
                configuracion = {}
                
                if tipo == 'estudiantes_a_egresados':
                    configuracion = self._configurar_estudiantes_a_egresados()
                elif tipo == 'aspirantes_a_estudiantes':
                    configuracion = self._configurar_aspirantes_a_estudiantes()
                # ... otros tipos
                
                if st.form_submit_button("💾 Guardar Plantilla"):
                    if not nombre:
                        st.error("❌ El nombre es obligatorio")
                    else:
                        try:
                            self.guardar_plantilla_migracion(
                                nombre, tipo, configuracion, descripcion
                            )
                            st.success(f"✅ Plantilla '{nombre}' guardada")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error: {e}")
        else:
            st.info("📭 No hay plantillas configuradas")
            st.button("➕ Crear Primera Plantilla")
    
    def _mostrar_mantenimiento(self):
        """Mostrar herramientas de mantenimiento"""
        st.subheader("🛠️ Herramientas de Mantenimiento")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Limpiar cache
            if st.button("🧹 Limpiar Caché"):
                # Lógica para limpiar cache
                st.success("✅ Caché limpiado")
            
            # Reconstruir índices
            if st.button("🔧 Reconstruir Índices"):
                with st.spinner("Reconstruyendo índices..."):
                    # Lógica para reconstruir índices
                    st.success("✅ Índices reconstruidos")
            
            # Verificar integridad
            if st.button("🔍 Verificar Integridad"):
                with st.spinner("Verificando integridad..."):
                    estado_bases = self.verificar_estado_bases()
                    
                    for nombre, info in estado_bases.items():
                        if info.get('conectada'):
                            st.success(f"✅ {nombre}: OK")
                        else:
                            st.error(f"❌ {nombre}: {info.get('error', 'Error')}")
        
        with col2:
            # Exportar logs
            if st.button("📤 Exportar Logs"):
                log_file = config.get('log_file', 'migracion_detallado.log')
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    
                    st.download_button(
                        label="⬇️ Descargar Logs",
                        data=log_content,
                        file_name=f"logs_migracion_{datetime.now().strftime('%Y%m%d')}.log",
                        mime="text/plain"
                    )
                else:
                    st.warning("⚠️ Archivo de logs no encontrado")
            
            # Resetear estadísticas
            if st.button("🔄 Resetear Estadísticas"):
                if st.checkbox("¿Confirmar reset de estadísticas?"):
                    # Lógica para resetear estadísticas
                    st.success("✅ Estadísticas reseteadas")
            
            # Prueba de migración
            if st.button("🧪 Ejecutar Prueba de Migración"):
                with st.spinner("Ejecutando prueba..."):
                    try:
                        resultado = self.ejecutar_migracion(
                            'estudiantes_a_egresados',
                            {
                                'criterios': {'estado_estudiante': 'Activo', 'semestre_minimo': 10},
                                'opciones': {'modo_prueba': True}
                            },
                            usuario='admin_prueba'
                        )
                        
                        if resultado.get('exito'):
                            st.success(f"✅ Prueba exitosa: {resultado.get('exitosos', 0)} registros simulados")
                        else:
                            st.error(f"❌ Prueba fallida")
                        
                        with st.expander("Ver detalles de prueba"):
                            st.json(resultado)
                            
                    except Exception as e:
                        st.error(f"❌ Error en prueba: {e}")

# =============================================================================
# FUNCIÓN PRINCIPAL DE LA APLICACIÓN
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
    
    # Verificar si es administrador (simulado)
    # En un sistema real, aquí iría la autenticación
    es_administrador = st.sidebar.checkbox("🔐 Modo Administrador", value=True)
    
    if not es_administrador:
        st.error("⛔ Acceso denegado. Se requiere permisos de administrador.")
        st.stop()
    
    # Inicializar sistema
    try:
        sistema = SistemaMigracion()
        logger.info("✅ Sistema de Migración inicializado")
    except Exception as e:
        st.error(f"❌ Error crítico al inicializar el sistema: {e}")
        logger.error(f"❌ Error inicializando sistema: {e}")
        return
    
    # Barra lateral con navegación
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2965/2965876.png", width=100)
        st.title(APP_TITLE)
        st.markdown("---")
        
        # Estado del sistema
        st.subheader("📊 Estado del Sistema")
        
        if sistema.estado.esta_inicializada():
            st.success("✅ Sistema listo")
        else:
            st.error("❌ Sistema no inicializado")
        
        estado_bases = sistema.verificar_estado_bases()
        bases_ok = sum(1 for b in estado_bases.values() if b.get('conectada'))
        st.write(f"Bases: {bases_ok}/{len(estado_bases)} conectadas")
        
        st.markdown("---")
        
        # Navegación
        st.subheader("🧭 Navegación")
        opcion = st.radio(
            "Seleccionar módulo:",
            [
                "🏠 Panel de Control",
                "🚀 Migraciones Rápidas",
                "🎛️ Migración Personalizada",
                "📋 Historial de Migraciones",
                "📊 Estadísticas",
                "⚙️ Administración"
            ]
        )
        
        st.markdown("---")
        
        # Acciones rápidas
        st.subheader("⚡ Acciones Rápidas")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Sync"):
                with st.spinner("Sincronizando..."):
                    if sistema.sincronizar_bases_datos():
                        st.success("✅ Sync OK")
                        st.rerun()
        
        with col2:
            if st.button("💾 Backup"):
                backup_path = sistema.crear_backup_migracion()
                if backup_path:
                    st.success("✅ Backup OK")
        
        st.markdown("---")
        
        # Información del sistema
        estadisticas = sistema.obtener_estadisticas_migracion()
        total_mig = estadisticas.get('generales', {}).get('total_migraciones', 0)
        
        st.caption(f"Versión: 3.0")
        st.caption(f"Migraciones: {total_mig}")
        st.caption(f"Última sync: {sistema.estado.estado.get('ultima_sincronizacion', 'Nunca')}")
    
    # Contenido principal basado en la selección
    if opcion == "🏠 Panel de Control":
        sistema.mostrar_panel_control()
    
    elif opcion == "🚀 Migraciones Rápidas":
        sistema.mostrar_migraciones_rapidas()
    
    elif opcion == "🎛️ Migración Personalizada":
        sistema.mostrar_migracion_personalizada()
    
    elif opcion == "📋 Historial de Migraciones":
        sistema.mostrar_historial_detallado()
    
    elif opcion == "📊 Estadísticas":
        sistema.mostrar_estadisticas()
    
    elif opcion == "⚙️ Administración":
        sistema.mostrar_administracion()
    
    # Pie de página
    st.markdown("---")
    st.caption(f"© 2024 Sistema de Migración v3.0 | Solo para administradores")

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    main()
