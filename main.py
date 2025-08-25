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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- FUNCIÓN DE SCRAPING CON REINTENTOS ---
def obtener_precio_por_kilo(url_producto, index):
    print(f"--- Iniciando scraping para: {url_producto} ---")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_argument("window-size=1280,800")

    driver = None
    # Bucle de reintentos (hasta 3 intentos)
    for intento in range(1, 4):
        try:
            print(f"   -> Intento #{intento}...")
            if driver is None:
                service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            
            driver.get(url_producto)
            
            wait = WebDriverWait(driver, 20) # 20 segundos de espera por intento
            precio_element = wait.until(
                EC.visibility_of_element_located((By.XPATH, "//span[contains(text(), 'x kg')]"))
            )
            
            # Si llegamos aquí, encontramos el precio
            texto_precio = precio_element.text
            match = re.search(r'\((.*?)\)', texto_precio)
            if match:
                texto_precio_kg = match.group(1)
                numeros = re.findall(r'\d+', texto_precio_kg)
                if numeros:
                    precio_final = int("".join(numeros))
                    print(f"   -> ¡Éxito en el intento #{intento}! Precio encontrado: {precio_final}")
                    if driver:
                        driver.quit()
                    return precio_final
            
            # Si algo raro pasa (ej. el elemento existe pero no tiene el formato esperado)
            print("   -> Elemento encontrado pero formato de precio incorrecto.")
            break # Salimos del bucle si el formato es raro

        except TimeoutException:
            print("   -> Timeout. El elemento del precio no apareció.")
            try:
                # Si falla, buscamos el botón "REINTENTAR"
                reintentar_button = driver.find_element(By.XPATH, "//button[contains(text(), 'REINTENTAR')]")
                print("   -> Botón 'REINTENTAR' encontrado. Haciendo clic y esperando...")
                reintentar_button.click()
                time.sleep(5) # Esperamos 5 segundos después de hacer clic
            except NoSuchElementException:
                print("   -> No se encontró el botón 'REINTENTAR'. Rindiéndose para esta URL.")
                break # Salimos del bucle si no hay botón de reintento
        
        except Exception as e:
            print(f"   -> ERROR inesperado en el intento #{intento}: {e}")
            time.sleep(5) # Pausa antes del siguiente intento

    # Si salimos del bucle sin éxito
    print(f"   -> No se pudo obtener el precio para {url_producto} después de 3 intentos.")
    if driver:
        screenshot_path = f"error_screenshot_{index}.png"
        driver.save_screenshot(screenshot_path)
        print(f"   -> Captura de pantalla final guardada en: {screenshot_path}")
        driver.quit()
    return None

# --- FUNCIÓN PRINCIPAL (SIN CAMBIOS) ---
def main():
    print("Iniciando el proceso de actualización de precios...")
    
    if 'GSPREAD_CREDENTIALS' in os.environ:
        creds_json = json.loads(os.environ['GSPREAD_CREDENTIALS'])
        gc = gspread.service_account_from_dict(creds_json)
        print("Autenticado con Google Sheets usando credenciales de GitHub Secrets.")
    else:
        gc = gspread.service_account(filename='credentials.json')
        print("Autenticado con Google Sheets usando el archivo local 'credentials.json'.")

    spreadsheet = gc.open("Precios GM") 
    worksheet = spreadsheet.worksheet("Jumbo-info") 
    print(f"Abierta la hoja de cálculo '{spreadsheet.title}' y la pestaña '{worksheet.title}'.")

    df = pd.DataFrame(worksheet.get_all_records())
    
    if 'URL' not in df.columns:
        print("ERROR: La hoja de cálculo debe tener una columna llamada 'URL'.")
        return

    for index, row in df.iterrows():
        url = row['URL']
        if url:
            precio = obtener_precio_por_kilo(url, index)
            if precio is not None:
                df.loc[index, 'Precio x KG'] = precio
                df.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            else:
                df.loc[index, 'Precio x KG'] = "ERROR"
                df.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            time.sleep(2) 

    print("Proceso de scraping finalizado. Actualizando la hoja de cálculo...")
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
    print("¡Hoja de cálculo actualizada con éxito!")

if __name__ == '__main__':
    main()
