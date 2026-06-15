from log import get_logger
from transcripcion import transcribir_audio
from analysis import analizar_transcripcion
from sql_connection import guardar_transcripcion, guardar_analisis
from connection_settings import AI_PROVIDER, PROCESSING_FEATURES
from token_manager import get_token_manager
import json
import os
import glob
import traceback

logger = get_logger()
token_manager = get_token_manager()


def _leer_archivo_con_encodings(ruta, encodings_to_try):
    """
    Helper para leer archivo con múltiples encodings
    
    Args:
        ruta: Ruta del archivo
        encodings_to_try: Lista de encodings a probar
    
    Returns:
        str: Contenido del archivo o None si falla
    """
    for encoding in encodings_to_try:
        try:
            with open(ruta, "r", encoding=encoding) as f:
                content = f.read()
            logger.debug(f"Archivo leído con encoding: {encoding}")
            return content
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        except Exception as e:
            logger.debug(f"Error con {encoding}: {e}")
            continue
    return None


def _crear_archivos_vacios(archivo_original, razon="Audio ininteligible"):
    """
    Crea archivos vacíos/mínimos cuando no hay transcripción válida
    
    Args:
        archivo_original: Ruta del archivo de audio
        razon: Razón por la que no hay transcripción
    
    Returns:
        tuple: (transcription_path, json_path)
    """
    base, _ = os.path.splitext(archivo_original)
    
    # 1. Crear transcripción vacía con mensaje
    ruta_transcripcion = f"{base};transcripcion.txt"
    mensaje_transcripcion = f"[NO HAY TRANSCRIPCIÓN VÁLIDA]\nRazón: {razon}\n"
    
    try:
        with open(ruta_transcripcion, "w", encoding="utf-8") as f:
            f.write(mensaje_transcripcion)
        logger.info(f"✓ Transcripción vacía creada: {ruta_transcripcion}")
    except Exception as e:
        logger.error(f"✗ Error creando transcripción vacía: {e}")
        raise
    
    # 2. Crear JSON de separación vacío
    proveedor_nombre = AI_PROVIDER.upper()
    ruta_transcripcion_json = f"{base};transcripcion.json"
    
    transcripcion_vacia = {
        "transcription": [
            {
                "type": "Sistema",
                "message": f"No se pudo obtener transcripción válida. {razon}"
            }
        ],
        "metadata": {
            "razon": razon,
            "audio_procesado": True,
            "transcripcion_valida": False
        }
    }
    
    try:
        with open(ruta_transcripcion_json, "w", encoding="utf-8") as f:
            json.dump(transcripcion_vacia, f, ensure_ascii=False, indent=4)
        logger.info(f"✓ JSON de transcripción vacío creado: {ruta_transcripcion_json}")
    except Exception as e:
        logger.error(f"✗ Error creando JSON vacío: {e}")
        raise
    
    return ruta_transcripcion, ruta_transcripcion_json


def procesar_transcripcion(transaction_id, archivo_original):
    """
    Procesa solo la transcripción del audio
    MODIFICADO: Maneja audio ininteligible creando archivos vacíos
    
    Args:
        transaction_id: ID de la transacción
        archivo_original: Ruta del archivo de audio
    
    Returns:
        tuple: (success: bool, tokens_in: int, tokens_out: int, transcription_path: str)
    """
    logger.info(f"🎤 Transcribiendo TransactionId: {transaction_id} - {archivo_original}")
    
    # ERROR CRÍTICO: Archivo no existe
    if not os.path.exists(archivo_original):
        logger.error(f"✗ ERROR CRÍTICO: Archivo no existe: {archivo_original}")
        raise FileNotFoundError(f"Archivo no existe: {archivo_original}")
    
    # WARNING: Feature deshabilitada
    if not PROCESSING_FEATURES.get('transcription_enabled', True):
        logger.warning("⚠ WARNING: Transcripción deshabilitada en configuración")
        return False, 0, 0, None
    
    try:
        # ERROR CRÍTICO: Límite de tokens excedido
        can_process, reason, usage_info = token_manager.can_process(estimated_tokens=3000)
        
        if not can_process:
            logger.error(f"✗ ERROR CRÍTICO: Límite de tokens excedido - {reason}")
            raise RuntimeError(f"Límite de tokens excedido: {reason}")
        
        # Realizar transcripción
        transcripcion = transcribir_audio(archivo_original)
        
        # CAMBIO PRINCIPAL: Si no hay transcripción válida, crear archivos vacíos
        if not transcripcion:
            logger.warning(
                f"⚠ WARNING: No se obtuvo transcripción válida para TransactionId {transaction_id}"
            )
            
            # Crear archivos vacíos para que el registro se complete
            ruta_transcripcion, ruta_json = _crear_archivos_vacios(
                archivo_original,
                razon="Audio sin voz válida, muy corto o ininteligible"
            )
            
            # Calcular tokens mínimos (prácticamente 0)
            estimated_tokens_in = 10
            estimated_tokens_out = 5
            
            # Guardar en BD como completado (con transcripción vacía)
            # IMPORTANTE: Guardamos la ruta del JSON para consistencia
            try:
                nombre_transcripcion = os.path.basename(ruta_json)
                guardar_transcripcion(
                    transaction_id,
                    ruta_json,  # Guardamos el JSON, no el TXT
                    nombre_transcripcion,
                    estimated_tokens_in,
                    estimated_tokens_out
                )
                logger.info(
                    f"✓ Transcripción vacía guardada en BD para {transaction_id} "
                    f"(audio ininteligible)"
                )
            except Exception as e:
                logger.error(f"✗ ERROR CRÍTICO: No se pudo guardar en BD: {e}")
                raise
            
            # Registrar uso mínimo de tokens
            token_manager.log_token_usage(
                estimated_tokens_in,
                estimated_tokens_out,
                "transcription"
            )
            
            # Retornar TRUE para que se marque como completado
            # El análisis podrá proceder con la transcripción vacía
            return True, estimated_tokens_in, estimated_tokens_out, ruta_json  # Retornamos el JSON
        
        # Caso normal: hay transcripción válida
        estimated_tokens_in = len(archivo_original.encode('utf-8')) // 4
        estimated_tokens_out = len(transcripcion.split())
        
        # Guardar transcripción en archivo
        base, _ = os.path.splitext(archivo_original)
        ruta_transcripcion = f"{base};transcripcion.txt"
        
        try:
            with open(ruta_transcripcion, "w", encoding="utf-8") as f:
                f.write(transcripcion)
            logger.info(f"✓ Transcripción guardada: {ruta_transcripcion}")
        except Exception as e:
            logger.error(f"✗ ERROR CRÍTICO: No se pudo guardar transcripción: {e}")
            raise
        
        # ==================== CÓDIGO NUEVO ====================
        # Crear JSON con separación Agente/Cliente INMEDIATAMENTE
        ruta_transcripcion_json = f"{base};transcripcion.json"
        tokens_separacion_in = 0
        tokens_separacion_out = 0
        
        try:
            from analysis import get_ai_provider, extraer_json_de_texto
            
            ai_provider = get_ai_provider()
            
            prompt_separacion = f"""
Transcribe y separa la conversación dada en bloques hablados por el Agente o el Cliente.
Devuelve el resultado exclusivamente en formato JSON con esta estructura exacta:

{{
  "transcription": [
    {{"type": "Agente", "message": "Texto del agente"}},
    {{"type": "Cliente", "message": "Texto del cliente"}}
  ]
}}

Aquí está la transcripción original para analizar:
{transcripcion}
"""
            
            logger.info(f"🔀 Separando conversación Agente/Cliente con {ai_provider.get_provider_name()}...")
            texto_respuesta, tokens_sep_in, tokens_sep_out = ai_provider.generate_response(
                prompt_separacion,
                max_tokens=4000
            )
            
            tokens_separacion_in = tokens_sep_in
            tokens_separacion_out = tokens_sep_out
            
            if texto_respuesta:
                transcripcion_json = extraer_json_de_texto(texto_respuesta)
                
                if "transcription" in transcripcion_json:
                    # Guardar JSON separado
                    with open(ruta_transcripcion_json, "w", encoding="utf-8") as f:
                        json.dump(transcripcion_json, f, ensure_ascii=False, indent=4)
                    logger.info(f"✓ JSON de transcripción separado creado: {ruta_transcripcion_json}")
                    logger.info(f"  Tokens separación - IN: {tokens_sep_in}, OUT: {tokens_sep_out}")
                else:
                    logger.warning("⚠ No se pudo separar - creando formato simple")
                    transcripcion_json = {
                        "transcription": [
                            {"type": "Desconocido", "message": transcripcion}
                        ]
                    }
                    with open(ruta_transcripcion_json, "w", encoding="utf-8") as f:
                        json.dump(transcripcion_json, f, ensure_ascii=False, indent=4)
            else:
                logger.warning("⚠ No se obtuvo respuesta de IA para separación")
                transcripcion_json = {
                    "transcription": [
                        {"type": "Desconocido", "message": transcripcion}
                    ]
                }
                with open(ruta_transcripcion_json, "w", encoding="utf-8") as f:
                    json.dump(transcripcion_json, f, ensure_ascii=False, indent=4)
                    
        except Exception as e:
            logger.warning(f"⚠ Error al separar transcripción con IA: {e}")
            # Crear JSON simple sin separación como fallback
            transcripcion_json = {
                "transcription": [
                    {"type": "Desconocido", "message": transcripcion}
                ]
            }
            try:
                with open(ruta_transcripcion_json, "w", encoding="utf-8") as f:
                    json.dump(transcripcion_json, f, ensure_ascii=False, indent=4)
                logger.info(f"✓ JSON simple creado (fallback): {ruta_transcripcion_json}")
            except Exception as e2:
                logger.error(f"✗ Error creando JSON fallback: {e2}")
        
        # Actualizar totales de tokens incluyendo la separación
        estimated_tokens_in += tokens_separacion_in
        estimated_tokens_out += tokens_separacion_out
        # ==================== FIN CÓDIGO NUEVO ====================
        
        # Guardar en base de datos usando SetTranscription
        # IMPORTANTE: Guardamos la ruta del JSON (con separación Agente/Cliente)
        # para que la interfaz web pueda mostrar la conversación estructurada
        try:
            nombre_transcripcion = os.path.basename(ruta_transcripcion_json)
            guardar_transcripcion(
                transaction_id,
                ruta_transcripcion_json,  # Guardamos el JSON, no el TXT
                nombre_transcripcion,
                estimated_tokens_in,
                estimated_tokens_out
            )
        except Exception as e:
            logger.error(f"✗ ERROR CRÍTICO: No se pudo guardar en BD: {e}")
            raise
        
        # Registrar uso de tokens
        token_manager.log_token_usage(
            estimated_tokens_in,
            estimated_tokens_out,
            "transcription"
        )
        
        logger.info(f"✓ Transcripción completada para {transaction_id}")
        return True, estimated_tokens_in, estimated_tokens_out, ruta_transcripcion_json  # Devolver JSON
        
    except (FileNotFoundError, RuntimeError):
        # ERRORES CRÍTICOS: Propagar hacia arriba
        raise
        
    except Exception as e:
        # ERROR CRÍTICO: Excepción inesperada
        logger.error(f"✗ ERROR CRÍTICO en procesar_transcripcion: {e}", exc_info=True)
        raise


def _crear_analisis_vacio(archivo_original, razon="Sin transcripción válida"):
    """
    Crea análisis vacío cuando no hay transcripción válida
    
    Args:
        archivo_original: Ruta del archivo de audio
        razon: Razón del análisis vacío
    
    Returns:
        tuple: (evaluacion_path_json, evaluacion_path_txt)
    """
    from datetime import datetime
    
    base, _ = os.path.splitext(archivo_original)
    nombre_base = os.path.basename(base)
    
    # Estructura de evaluación vacía
    evaluacion_vacia = {
        "id_llamada": nombre_base,
        "fecha_evaluacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ruta_audio": archivo_original,
        "proveedor_ia": AI_PROVIDER.upper(),
        "modelo": "N/A",
        "criterios": {
            "saludo_presentacion": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "verificacion_cliente": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "escucha_activa": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "identificacion_necesidad": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "conocimiento_producto": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "ofrecimiento_solucion": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "manejo_objeciones": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "empatia_tono": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "cierre_despedida": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0},
            "cumplimiento_protocolo": {"comentario": "No evaluable - sin transcripción", "puntuacion": 0}
        },
        "scores": {
            "puntuacion_final": 0,
            "puntuacion_transcripcion": 0
        },
        "recomendacion": f"No se pudo realizar evaluación. {razon}",
        "transcripcion_json": {
            "transcription": [
                {"type": "Sistema", "message": razon}
            ]
        },
        "tokens_used": {
            "input": 0,
            "output": 0,
            "total": 0
        },
        "metadata": {
            "razon": razon,
            "evaluacion_valida": False
        }
    }
    
    ruta_evaluacion_json = f"{base};evaluacion.json"
    ruta_evaluacion_txt = f"{base};evaluacion.txt"
    
    try:
        with open(ruta_evaluacion_json, "w", encoding="utf-8") as f:
            json.dump(evaluacion_vacia, f, ensure_ascii=False, indent=4)
        
        with open(ruta_evaluacion_txt, "w", encoding="utf-8") as f:
            f.write(json.dumps(evaluacion_vacia, ensure_ascii=False, indent=4))
        
        logger.info(f"✓ Análisis vacío creado: {ruta_evaluacion_json}")
        return ruta_evaluacion_json, ruta_evaluacion_txt
        
    except Exception as e:
        logger.error(f"✗ Error creando análisis vacío: {e}")
        raise


def procesar_analisis(transaction_id, archivo_original, ruta_transcripcion=None):
    """
    Procesa solo el análisis de la transcripción
    MODIFICADO: Maneja transcripciones vacías creando análisis vacío
    
    Args:
        transaction_id: ID de la transacción
        archivo_original: Ruta del archivo de audio original
        ruta_transcripcion: Ruta del archivo de transcripción (opcional)
    
    Returns:
        tuple: (success: bool, tokens_in: int, tokens_out: int)
    """
    logger.info(f"📊 Analizando TransactionId: {transaction_id}")
    
    # WARNING: Feature deshabilitada
    if not PROCESSING_FEATURES.get('analysis_enabled', True):
        logger.warning("⚠ WARNING: Análisis deshabilitado en configuración")
        return False, 0, 0
    
    try:
        # Cargar transcripción con búsqueda robusta
        transcripcion = None
        encodings_to_try = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252']
        ruta_usada = None
        
        # ESTRATEGIA 1: Usar path de BD si existe y es válido
        if ruta_transcripcion and os.path.exists(ruta_transcripcion):
            logger.info(f"Usando TranscriptionPath de BD: {ruta_transcripcion}")
            transcripcion = _leer_archivo_con_encodings(ruta_transcripcion, encodings_to_try)
            if transcripcion:
                ruta_usada = ruta_transcripcion
        
        # ESTRATEGIA 2: Construir path normalizando : → ; (Windows hace esto)
        if not transcripcion:
            base, _ = os.path.splitext(archivo_original)
            base_normalizado = base.replace(':', ';')
            ruta_candidata = f"{base_normalizado};transcripcion.txt"
            
            if os.path.exists(ruta_candidata):
                logger.info(f"Archivo encontrado con normalización: {ruta_candidata}")
                transcripcion = _leer_archivo_con_encodings(ruta_candidata, encodings_to_try)
                if transcripcion:
                    ruta_usada = ruta_candidata
        
        # ESTRATEGIA 3: Buscar con glob pattern en el directorio
        if not transcripcion:
            try:
                directorio = os.path.dirname(base_normalizado if 'base_normalizado' in locals() else archivo_original)
                patron = os.path.join(directorio, f"*transcripcion.txt")
                
                logger.debug(f"Buscando con glob: {patron}")
                archivos = glob.glob(patron)
                
                if archivos:
                    nombre_audio = os.path.basename(archivo_original).replace(':', ';')
                    nombre_base = os.path.splitext(nombre_audio)[0]
                    
                    for archivo in archivos:
                        if nombre_base in os.path.basename(archivo):
                            logger.info(f"Archivo encontrado con glob: {archivo}")
                            transcripcion = _leer_archivo_con_encodings(archivo, encodings_to_try)
                            if transcripcion:
                                ruta_usada = archivo
                                break
                    
                    if not transcripcion and archivos:
                        logger.debug(f"Usando primer archivo encontrado: {archivos[0]}")
                        transcripcion = _leer_archivo_con_encodings(archivos[0], encodings_to_try)
                        if transcripcion:
                            ruta_usada = archivos[0]
            except Exception as e:
                logger.debug(f"Error en búsqueda glob: {e}")
        
        # WARNING: No se encontró transcripción
        if not transcripcion:
            logger.warning(
                f"⚠ WARNING: No se encontró transcripción para TransactionId {transaction_id}. "
                f"Probablemente la transcripción aún no se ha completado."
            )
            logger.debug(f"  Audio original: {archivo_original}")
            logger.debug(f"  Path de BD: {ruta_transcripcion}")
            if 'ruta_candidata' in locals():
                logger.debug(f"  Path esperado: {ruta_candidata}")
            return False, 0, 0
        
        logger.info(f"✓ Transcripción cargada exitosamente desde: {ruta_usada}")
        
        # CAMBIO PRINCIPAL: Detectar transcripción vacía y crear análisis vacío
        if "[NO HAY TRANSCRIPCIÓN VÁLIDA]" in transcripcion or not transcripcion.strip():
            logger.warning(f"⚠ Transcripción vacía detectada para {transaction_id}")
            
            # Crear análisis vacío
            ruta_evaluacion_json, ruta_evaluacion_txt = _crear_analisis_vacio(
                archivo_original,
                razon="Audio ininteligible - sin transcripción válida"
            )
            
            # Guardar en BD con tokens mínimos
            tokens_in = 5
            tokens_out = 5
            
            try:
                nombre_analisis = os.path.basename(ruta_evaluacion_json)
                guardar_analisis(
                    transaction_id,
                    ruta_evaluacion_json,
                    nombre_analisis,
                    tokens_in,
                    tokens_out
                )
                logger.info(f"✓ Análisis vacío guardado en BD para {transaction_id}")
            except Exception as e:
                logger.error(f"✗ ERROR CRÍTICO: No se pudo guardar análisis en BD: {e}")
                raise
            
            # Registrar uso mínimo de tokens
            token_manager.log_token_usage(tokens_in, tokens_out, "analysis")
            
            # Retornar TRUE para que se marque como completado
            return True, tokens_in, tokens_out
        
        # Caso normal: hay transcripción válida
        estimated_tokens_for_analysis = len(transcripcion.split()) * 2
        
        # ERROR CRÍTICO: Límite de tokens excedido
        can_process, reason, usage_info = token_manager.can_process(
            estimated_tokens=estimated_tokens_for_analysis
        )
        
        if not can_process:
            logger.error(f"✗ ERROR CRÍTICO: Límite de tokens excedido para análisis - {reason}")
            raise RuntimeError(f"Límite de tokens excedido: {reason}")
        
        # Realizar análisis con el proveedor de IA
        evaluacion = analizar_transcripcion(transcripcion, archivo_original)
        
        # Obtener tokens reales del análisis
        tokens_in = evaluacion.get('tokens_used', {}).get('input', estimated_tokens_for_analysis // 2)
        tokens_out = evaluacion.get('tokens_used', {}).get('output', estimated_tokens_for_analysis // 2)
        
        # Guardar evaluación en archivos
        base, _ = os.path.splitext(archivo_original)
        ruta_evaluacion_txt = f"{base};evaluacion.txt"
        ruta_evaluacion_json = f"{base};evaluacion.json"
        
        try:
            with open(ruta_evaluacion_json, "w", encoding="utf-8") as f:
                json.dump(evaluacion, f, ensure_ascii=False, indent=4)
            
            with open(ruta_evaluacion_txt, "w", encoding="utf-8") as f:
                f.write(json.dumps(evaluacion, ensure_ascii=False, indent=4))
            
            logger.info(f"✓ Análisis guardado: {ruta_evaluacion_json}")
        except Exception as e:
            logger.error(f"✗ ERROR CRÍTICO: No se pudo guardar análisis: {e}")
            raise
        
        # Guardar en base de datos usando SetAnalysis
        try:
            nombre_analisis = os.path.basename(ruta_evaluacion_json)
            guardar_analisis(
                transaction_id,
                ruta_evaluacion_json,
                nombre_analisis,
                tokens_in,
                tokens_out
            )
        except Exception as e:
            logger.error(f"✗ ERROR CRÍTICO: No se pudo guardar análisis en BD: {e}")
            raise
        
        # Registrar uso de tokens
        token_manager.log_token_usage(tokens_in, tokens_out, "analysis")
        
        logger.info(f"✓ Análisis completado para {transaction_id}")
        return True, tokens_in, tokens_out
        
    except RuntimeError:
        # ERROR CRÍTICO: Propagar hacia arriba
        raise
        
    except Exception as e:
        # ERROR CRÍTICO: Excepción inesperada
        logger.error(f"✗ ERROR CRÍTICO en procesar_analisis: {e}", exc_info=True)
        raise


def procesar_audio_completo(transaction_id, archivo_original):
    """
    Procesa transcripción + análisis (para compatibilidad con código anterior)
    
    Args:
        transaction_id: ID de la transacción
        archivo_original: Ruta del archivo de audio
    
    Returns:
        tuple: (success: bool, total_tokens_in: int, total_tokens_out: int)
    """
    logger.info(f"✓ Procesamiento completo - TransactionId: {transaction_id}")
    
    # Paso 1: Transcripción
    try:
        transcription_success, transcription_in, transcription_out, transcription_path = procesar_transcripcion(
            transaction_id,
            archivo_original
        )
    except Exception as e:
        # ERROR CRÍTICO en transcripción
        logger.error(f"✗ ERROR CRÍTICO en transcripción: {e}")
        return False, 0, 0
    
    if not transcription_success:
        # WARNING: No se obtuvo transcripción (ya logueado en la función)
        return False, 0, 0
    
    # Paso 2: Análisis (si está habilitado)
    if PROCESSING_FEATURES.get('analysis_enabled', True):
        try:
            analysis_success, analysis_in, analysis_out = procesar_analisis(
                transaction_id,
                archivo_original,
                transcription_path
            )
        except Exception as e:
            # ERROR CRÍTICO en análisis
            logger.error(f"✗ ERROR CRÍTICO en análisis: {e}")
            logger.warning("⚠ Transcripción completada pero análisis falló")
            return True, transcription_in, transcription_out
        
        if not analysis_success:
            logger.warning("⚠ WARNING: Análisis no completado, pero transcripción exitosa")
            return True, transcription_in, transcription_out
        
        return True, transcription_in + analysis_in, transcription_out + analysis_out
    else:
        logger.info("Análisis omitido (deshabilitado)")
        return True, transcription_in, transcription_out


# Alias para compatibilidad con código existente
procesar_audio = procesar_audio_completo