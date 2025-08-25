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

# --- NO TOCAR: ESTA FUNCIÓN DE SCRAPING FUNCIONA PERFECTAMENTE ---
def obtener_precio_por_kilo(url_producto, index):
    print(f"--- Iniciando scraping para: {url_producto} ---")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    options.add_argument("window-size=1280,800")

    driver = None
    for intento in range(1, 4):
        try:
            print(f"   -> Intento #{intento}...")
            if driver is None:
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
                    print(f"   -> ¡Éxito en el intento #{intento}! Precio encontrado: {precio_final}")
                    if driver:
                        driver.quit()
                    return precio_final
            
            print("   -> Elemento encontrado pero formato de precio incorrecto.")
            break 

        except TimeoutException:
            print("   -> Timeout. El elemento del precio no apareció.")
            try:
                reintentar_button = driver.find_element(By.XPATH, "//button[contains(text(), 'REINTENTAR')]")
                print("   -> Botón 'REINTENTAR' encontrado. Haciendo clic y esperando...")
                reintentar_button.click()
                time.sleep(5) 
            except NoSuchElementException:
                print("   -> No se encontró el botón 'REINTENTAR'. Rindiéndose para esta URL.")
                break 
        
        except Exception as e:
            print(f"   -> ERROR inesperado en el intento #{intento}: {e}")
            time.sleep(5)

    print(f"   -> No se pudo obtener el precio para {url_producto} después de 3 intentos.")
    if driver:
        # Ya no guardamos capturas porque el proceso funciona, pero lo dejamos por si acaso.
        # screenshot_path = f"error_screenshot_{index}.png"
        # driver.save_screenshot(screenshot_path)
        # print(f"   -> Captura de pantalla final guardada en: {screenshot_path}")
        driver.quit()
    return None

# --- FUNCIÓN PRINCIPAL MODIFICADA ---
def main():
    print("Iniciando el proceso de actualización de precios...")
    
    # 1. AUTENTICACIÓN (Sin cambios)
    if 'GSPREAD_CREDENTIALS' in os.environ:
        creds_json = json.loads(os.environ['GSPREAD_CREDENTIALS'])
        gc = gspread.service_account_from_dict(creds_json)
        print("Autenticado con Google Sheets usando credenciales de GitHub Secrets.")
    else:
        gc = gspread.service_account(filename='credentials.json')
        print("Autenticado con Google Sheets usando el archivo local 'credentials.json'.")

    # 2. ABRIR AMBAS HOJAS DE CÁLCULO
    spreadsheet = gc.open("Precios GM") 
    worksheet_origen = spreadsheet.worksheet("Jumbo-info") 
    worksheet_destino = spreadsheet.worksheet("P-web")
    print(f"Abiertas las hojas '{worksheet_origen.title}' (origen) y '{worksheet_destino.title}' (destino).")

    # 3. LEER LOS DATOS DE AMBAS HOJAS
    df_origen = pd.DataFrame(worksheet_origen.get_all_records())
    df_destino = pd.DataFrame(worksheet_destino.get_all_records())
    
    # Asegurarse que las columnas necesarias existan
    if 'URL' not in df_origen.columns or 'SKU' not in df_origen.columns:
        print("ERROR: La hoja 'Jumbo-info' debe tener las columnas 'URL' y 'SKU'.")
        return
    if 'SKU' not in df_destino.columns or 'Jumbo Kg' not in df_destino.columns:
        print("ERROR: La hoja 'P-web' debe tener las columnas 'SKU' y 'Jumbo Kg'.")
        return

    # 4. PROCESAR, SCRAPEAR Y PREPARAR LA ACTUALIZACIÓN
    updates_count = 0
    for index, row_origen in df_origen.iterrows():
        url = str(row_origen['URL'])
        sku = row_origen['SKU']
        
        if url and sku: # Solo procesar si URL y SKU no están vacíos
            precio = obtener_precio_por_kilo(url, index)
            
            # Buscar el SKU en la hoja de destino
            # Usamos .loc para encontrar la fila donde el SKU coincida
            filas_destino = df_destino.loc[df_destino['SKU'] == sku]
            
            if not filas_destino.empty:
                # Obtenemos el índice de la primera fila que coincida
                indice_destino = filas_destino.index[0]
                
                # Actualizamos el DataFrame de destino con el nuevo precio
                if precio is not None:
                    df_destino.loc[indice_destino, 'Jumbo Kg'] = precio
                    updates_count += 1
                else:
                    df_destino.loc[indice_destino, 'Jumbo Kg'] = "ERROR"
                
                # También actualizamos la fecha en la hoja de origen
                df_origen.loc[index, 'Ultima Actualizacion'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            else:
                print(f"   -> ADVERTENCIA: No se encontró el SKU {sku} en la hoja 'P-web'.")

            time.sleep(2) 

    # 5. ACTUALIZAR AMBAS HOJAS DE CÁLCULO
    if updates_count > 0:
        print(f"Proceso de scraping finalizado. Se actualizarán {updates_count} precios.")
        print("Actualizando la hoja 'P-web'...")
        worksheet_destino.clear()
        worksheet_destino.update([df_destino.columns.values.tolist()] + df_destino.fillna('').values.tolist())
        print("Actualizando la hoja 'Jumbo-info' con las fechas...")
        worksheet_origen.clear()
        worksheet_origen.update([df_origen.columns.values.tolist()] + df_origen.fillna('').values.tolist())
        print("¡Hojas de cálculo actualizadas con éxito!")
    else:
        print("Proceso finalizado. No se encontraron precios para actualizar.")

if __name__ == '__main__':
    main()
