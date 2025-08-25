import gspread
import pandas as pd
import re
import time
import os
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- FUNCIÓN DE SCRAPING (SIN CAMBIOS) ---
def obtener_precio_por_kilo(url_producto):
    print(f"--- Iniciando scraping para: {url_producto} ---")
    options = webdriver.ChromeOptions()
    # Estas opciones son CRUCIALES para que funcione en GitHub Actions
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url_producto)
        
        wait = WebDriverWait(driver, 20)
        precio_element = wait.until(
            EC.visibility_of_element_located((By.XPATH, "//span[contains(text(), 'x kg')]"))
        )
        texto_precio = precio_element.text
        match = re.search(r'\((.*?)\)', texto_precio)
        if match:
            texto_precio_kg = match.group(1)
            numeros = re.findall(r'\d+', texto_precio_kg)
            if numeros:
                precio_final = int("".join(numeros))
                print(f"   -> Precio encontrado: {precio_final}")
                return precio_final
        return None
    except Exception as e:
        print(f"   -> ERROR al scrapear: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# --- FUNCIÓN PRINCIPAL PARA INTERACTUAR CON GOOGLE SHEETS ---
def main():
    print("Iniciando el proceso de actualización de precios...")
    
    # 1. AUTENTICACIÓN CON GOOGLE SHEETS
    # En GitHub Actions, las credenciales se leen desde una variable de entorno.
    # Localmente, busca un archivo 'credentials.json'.
    if 'GSPREAD_CREDENTIALS' in os.environ:
        creds_json = json.loads(os.environ['GSPREAD_CREDENTIALS'])
        gc = gspread.service_account_from_dict(creds_json)
        print("Autenticado con Google Sheets usando credenciales de GitHub Secrets.")
    else:
        # Asegúrate de tener tu archivo 'credentials.json' en la misma carpeta
        gc = gspread.service_account(filename='credentials.json')
        print("Autenticado con Google Sheets usando el archivo local 'credentials.json'.")

    # 2. ABRIR LA HOJA DE CÁLCULO
    # Reemplaza 'NombreDeTuHojaDeCalculo' con el nombre exacto de tu archivo en Google Drive.
    spreadsheet = gc.open("Precios GM") 
    # Puedes usar el nombre de la pestaña, ej: "Precios" o "Hoja 1"
    worksheet = spreadsheet.worksheet("Jumbo-info") 
    print(f"Abierta la hoja de cálculo '{spreadsheet.title}' y la pestaña '{worksheet.title}'.")

    # 3. LEER LOS DATOS Y PROCESARLOS
    # Leemos todos los datos y los convertimos a un DataFrame de pandas para manejarlos fácilmente.
    df = pd.DataFrame(worksheet.get_all_records())
    
    # Asegúrate de que tu hoja tenga estas columnas: 'URL', 'Precio x KG', 'Ultima Actualizacion'
    if 'URL' not in df.columns:
        print("ERROR: La hoja de cálculo debe tener una columna llamada 'URL'.")
        return

    for index, row in df.iterrows():
        url = row['URL']
        if url: # Solo procesar si la celda de URL no está vacía
            precio = obtener_precio_por_kilo(url)
            if precio is not None:
                # Actualizamos el DataFrame en la fila y columnas correspondientes.
                df.loc[index, 'Precio x KG'] = precio
                df.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            else:
                df.loc[index, 'Precio x KG'] = "ERROR"
                df.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            time.sleep(2) # Pequeña pausa para no sobrecargar el servidor de Jumbo

    # 4. ACTUALIZAR LA HOJA DE CÁLCULO CON LOS NUEVOS DATOS
    print("Proceso de scraping finalizado. Actualizando la hoja de cálculo...")
    # Borra todo el contenido de la hoja y lo reescribe con los datos actualizados del DataFrame.
    # Esto es más seguro que actualizar celda por celda.
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Hoja de cálculo actualizada con éxito!")

if __name__ == '__main__':
    main()
