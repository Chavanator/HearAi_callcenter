import socket
import json
import os
import datetime
import pyodbc
from pydub import AudioSegment
import speech_recognition as sr
import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()


# ==============================
# 1. CARGAR CONFIGURACIÓN
# ==============================
CONFIG_PATH = os.getenv("CONFIG_PATH", "config.json")

# Si no existe, crear plantilla base
if not os.path.exists(CONFIG_PATH):
    config = {
        "api_key": os.getenv("GEMINI_API_KEY", ""),
        "prompt": """Eres un evaluador de calidad de atención al cliente en un call center.
Analiza la siguiente transcripción y evalúa el desempeño del agente según esta rúbrica:

1. Saludo y presentación  
2. Verificación del cliente  
3. Escucha activa  
4. Identificación de la necesidad  
5. Conocimiento del producto/servicio  
6. Ofrecimiento de solución o alternativa  
7. Manejo de objeciones  
8. Empatía y tono  
9. Cierre y despedida  
10. Cumplimiento del protocolo  

Transcripción de la llamada:
{call_text}

Devuelve exclusivamente un JSON con la siguiente estructura:

{
  "id_llamada": "",
  "fecha": "",
  "criterios": {
    "saludo_presentacion": { "comentario": "", "puntuacion": 0 },
    "verificacion_cliente": { "comentario": "", "puntuacion": 0 },
    "escucha_activa": { "comentario": "", "puntuacion": 0 },
    "identificacion_necesidad": { "comentario": "", "puntuacion": 0 },
    "conocimiento_producto": { "comentario": "", "puntuacion": 0 },
    "ofrecimiento_solucion": { "comentario": "", "puntuacion": 0 },
    "manejo_objeciones": { "comentario": "", "puntuacion": 0 },
    "empatia_tono": { "comentario": "", "puntuacion": 0 },
    "cierre_despedida": { "comentario": "", "puntuacion": 0 },
    "cumplimiento_protocolo": { "comentario": "", "puntuacion": 0 }
  },
  "puntuacion_final": 0,
  "puntuacion_transcripcion": 0,
  "recomendacion": ""
}

No incluyas texto fuera del JSON.""",
        "db_connection": os.getenv("DB_CONNECTION", "DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=your_db;UID=sa;PWD=your_password")
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
else:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

# Configurar Gemini
api_key = config.get("api_key") or os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not set. Configure it in .env or config.json")
genai.configure(api_key=api_key)


# ==============================
# 2. FUNCIONES AUXILIARES
# ==============================

def transcribir_audio(archivo_original):
    archivo_convertido = "temp_pcm.wav"
    print(" Convirtiendo el audio...")
    sound = AudioSegment.from_file(archivo_original)
    sound = sound.set_frame_rate(16000).set_channels(1)
    sound.export(archivo_convertido, format="wav")

    recognizer = sr.Recognizer()
    audio = AudioSegment.from_wav(archivo_convertido)
    segment_duration = 60 * 1000
    num_segments = ceil(len(audio) / segment_duration)

    transcripcion = ""
    for i in range(num_segments):
        inicio = i * segment_duration
        fin = min((i + 1) * segment_duration, len(audio))
        fragmento = audio[inicio:fin]
        fragment_path = f"temp_fragment_{i}.wav"
        fragmento.export(fragment_path, format="wav")

        with sr.AudioFile(fragment_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = recognizer.record(source)

        try:
            texto = recognizer.recognize_google(audio_data, language="es-ES")
            transcripcion += texto + " "
            print(f"Fragmento {i+1}/{num_segments}: OK")
        except sr.UnknownValueError:
            print(f"Fragmento {i+1}/{num_segments}: no se entiende el audio.")
        except sr.RequestError as e:
            print(f"Error de conexion en el fragmento {i+1}: {e}")
            break
        finally:
            os.remove(fragment_path)

    os.remove(archivo_convertido)
    return transcripcion.strip()


def analizar_con_gemini(call_text: str, id_llamada: str):
    """Envía la transcripción a Gemini y devuelve el JSON estructurado."""
    prompt = config["prompt"].replace("{call_text}", call_text)

    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)

        # Intentar parsear el resultado como JSON
        json_str = response.text.strip()
        print(f"[DEBUG] Respuesta cruda:\n{json_str}")

        data = json.loads(json_str)
        data["id_llamada"] = id_llamada
        data["fecha"] = datetime.datetime.now().isoformat()
        return data

    except Exception as e:
        print(f"[ERROR] Gemini no devolvió JSON válido: {e}")
        return {
            "id_llamada": id_llamada,
            "fecha": datetime.datetime.now().isoformat(),
            "error": str(e)
        }


def ejecutar_sp(nombre_sp: str, params: tuple):
    """Ejecuta un stored procedure en SQL Server."""
    try:
        conn = pyodbc.connect(config["db_connection"])
        cursor = conn.cursor()
        cursor.execute(f"EXEC {nombre_sp} ?, ?, ?", params)
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[OK] Stored Procedure {nombre_sp} ejecutado con éxito.")
    except Exception as e:
        print(f"[ERROR] Error ejecutando SP {nombre_sp}: {e}")


# ==============================
# 3. SERVIDOR SOCKET
# ==============================

def iniciar_servidor(host="0.0.0.0", puerto=5050):
    """Inicia el servidor que escucha solicitudes para procesar audio."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, puerto))
    server.listen(5)
    print(f"[SERVIDOR] Escuchando en {host}:{puerto}...")

    while True:
        conn, addr = server.accept()
        print(f"[CONEXIÓN] Cliente conectado desde {addr}")

        try:
            data = conn.recv(4096).decode("utf-8")
            if not data:
                continue

            print(f"[RECIBIDO] {data}")
            request = json.loads(data)

            transaction_id = request["transaction_id"]
            audio_path = request["audio_path"]

            # 1. Transcribir
            texto = transcribir_audio(audio_path)
            transcription_name = f"transcripcion_{transaction_id}.txt"
            transcription_path = os.path.join("transcripciones", transcription_name)
            os.makedirs("transcripciones", exist_ok=True)

            with open(transcription_path, "w", encoding="utf-8") as f:
                f.write(texto)

            ejecutar_sp("SetTranscription", (transaction_id, transcription_path, transcription_name))

            # 2. Analizar con Gemini
            resultado = analizar_con_gemini(texto, str(transaction_id))
            analyzed_name = f"analisis_{transaction_id}.json"
            analyzed_path = os.path.join("analisis", analyzed_name)
            os.makedirs("analisis", exist_ok=True)

            with open(analyzed_path, "w", encoding="utf-8") as f:
                json.dump(resultado, f, ensure_ascii=False, indent=4)

            ejecutar_sp("SetAnalysis", (transaction_id, analyzed_path, analyzed_name))

            conn.sendall(b"OK\n")
            print("[OK] Proceso completado con éxito.\n")

        except Exception as e:
            print(f"[ERROR] {e}")
            conn.sendall(f"ERROR: {e}\n".encode("utf-8"))

        finally:
            conn.close()


# ==============================
# 4. MAIN
# ==============================
if __name__ == "__main__":
    iniciar_servidor()
