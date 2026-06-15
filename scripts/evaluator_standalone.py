#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
import speech_recognition as sr
from pydub import AudioSegment
from math import ceil
import json
import google.generativeai as genai


# In[ ]:


# === Cargar configuración ===
with open("AIvaluator_config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# === Configurar API Gemini ===
API_KEY = config["gemini"]["api_key"]
genai.configure(api_key=API_KEY)

# === Configurar rutas de audio ===
archivo_original = config["rutas_audio"]["archivo_original"]
archivo_convertido = config["rutas_audio"]["archivo_convertido"]

print("API Key cargada correctamente.")
print(f"Ruta original: {archivo_original}")
print(f"Ruta convertida: {archivo_convertido}")


# In[ ]:


# Conversion de codec
print("Convirtiendo el audio...")
sound = AudioSegment.from_file(archivo_original)
sound = sound.set_frame_rate(16000)
sound = sound.set_channels(1)
sound.export(archivo_convertido, format="wav")


# In[ ]:


# Reconocedor
recognizer = sr.Recognizer()

# Trozar audio
segment_duration = 60 * 1000  # milisegundos
audio = AudioSegment.from_wav(archivo_convertido)
num_segments = ceil(len(audio) / segment_duration)

print(f"Duracion total: {len(audio)/60000:.2f} min")
print(f"Dividiendo en {num_segments} fragmentos de 60s...")

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
        print(f"Fragmento {i+1}/{num_segments}: OK")
        transcripcion += texto + " "
    except sr.UnknownValueError:
        print(f"Fragmento {i+1}/{num_segments}: no se entiende el audio.")
    except sr.RequestError as e:
        print(f"Error de conexion en el fragmento {i+1}: {e}")
        break
    finally:
        os.remove(fragment_path)


# In[ ]:


# Rutas de salida
base, ext = os.path.splitext(archivo_original)
ruta_transcripcion = f"{base};transcripcion.txt"
ruta_evaluacion = f"{base};evaluacion.txt"


# In[ ]:


# gruadar transcripcion
if transcripcion.strip():
    print("\n--- TRANSCRIPCION COMPLETA ---\n")
    print(transcripcion)
    with open(ruta_transcripcion, "w", encoding="utf-8") as f:
        f.write(transcripcion)
    print(f"\nTranscripcion guardada en:\n{ruta_transcripcion}")
else:
    print("Atencion: No se pudo reconocer texto en el audio completo.")


# In[ ]:


# EVALUACION CON GEMINI
def analyze_call_gemini(call_text):
    prompt = f"""
Eres un evaluador de calidad de atención al cliente en un call center.
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

Devuelve un análisis detallado por punto, una puntuación final del 1 al 10, y una breve recomendación de mejora.
Como detalle adicional incluye una puntuación del 1-10 para la transcripción del audio.
    """

    model = genai.GenerativeModel("models/gemini-2.5-pro")
    response = model.generate_content(prompt)
    return response.text



# In[ ]:


# Analisis
if transcripcion.strip():
    analisis = analyze_call_gemini(transcripcion)
    print("\n--- RESULTADO DEL ANÁLISIS (Gemini) ---\n")
    print(analisis)

    # Guardar resultado
    with open(ruta_evaluacion, "w", encoding="utf-8") as f:
        f.write(analisis)
    print(f"\nEvaluacion guardada en:\n{ruta_evaluacion}")


# In[ ]:





# In[ ]:




