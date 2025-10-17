import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from pdfminer.high_level import extract_text
import tempfile
import os
import requests
from urllib.parse import urljoin

# -------- ENVÍO TELEGRAM --------
def enviar_telegram(mensaje):
    """Envía un mensaje al chat de Telegram configurado en las variables de entorno."""
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("⚠️ No hay TOKEN o CHAT_ID configurados.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": mensaje}
    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print(f"❌ Error al enviar mensaje Telegram: {e}")

# -------- FUNCIONES PRINCIPALES --------
async def obtener_url_ultimo_boletin():
    url = "https://www.juntadeandalucia.es/boja/"
    enviar_telegram("🔍 Entrando en la web del BOJA...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        shadow_host = await page.query_selector("matter-last-boja")
        shadow_root = await shadow_host.evaluate_handle("el => el.shadowRoot")
        enlace = await shadow_root.query_selector("a[aria-label*='ACCEDER AL ÚLTIMO BOJA']")
        href = await enlace.get_attribute("href")
        await browser.close()

        if not href.startswith("http"):
            href = "https://www.juntadeandalucia.es" + href

        enviar_telegram(f"➡️ Accedido al último boletín:\n{href}")
        return href

def obtener_enlace_sumario(url_boletin):
    enviar_telegram("📄 Buscando enlace al sumario del boletín...")
    try:
        r = requests.get(url_boletin, timeout=15)
        r.raise_for_status()
    except Exception as e:
        enviar_telegram(f"❌ Error al descargar la página del boletín: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.find("a", attrs={"title": lambda x: x and "sumario" in x.lower()})
    if not a:
        a = soup.find("a", string=lambda s: s and "sumario" in s.lower())
    if not a:
        pdf_links = soup.find_all("a", href=lambda h: h and h.lower().endswith(".pdf"))
        for link in pdf_links:
            if "sumario" in link.get("href", "").lower():
                a = link
                break
    if not a:
        enviar_telegram("❌ No se encontró el enlace al sumario.")
        return None

    href = a.get("href")
    if not href:
        enviar_telegram("❌ El enlace encontrado no tiene href.")
        return None

    url_sumario = urljoin(url_boletin, href)
    return url_sumario

def descargar_y_extraer_pdf(url_pdf):
    enviar_telegram("⬇️ Descargando y leyendo el sumario en PDF...")
    r = requests.get(url_pdf)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(r.content)
        tmp_path = tmp.name
    texto = extract_text(tmp_path)
    return texto

def buscar_frase(texto):
    objetivo = "Subvenciones en régimen de concurrencia no competitiva a organizaciones sindicales para la financiación de gastos corrientes"
    similitud = fuzz.partial_ratio(objetivo.lower(), texto.lower())
    return similitud


# -------- PROCESO PRINCIPAL --------
async def main():
    try:
        enviar_telegram("🚀 Iniciando proceso de comprobación del BOJA...")
        url_boletin = await obtener_url_ultimo_boletin()
        if not url_boletin:
            enviar_telegram("❌ No se pudo obtener el último boletín.")
            return

        url_sumario = obtener_enlace_sumario(url_boletin)
        if not url_sumario:
            return

        texto = descargar_y_extraer_pdf(url_sumario)
        similitud = buscar_frase(texto)

        enviar_telegram(f"🧠 Análisis completado. Similitud: {similitud}%")

        if similitud >= 80:
            enviar_telegram("✅ Frase encontrada con alta similitud. ¡Aviso importante!")
        else:
            enviar_telegram("⚠️ Frase no encontrada o con baja similitud.")
    except Exception as e:
        enviar_telegram(f"❌ Error general en el proceso: {e}")


if __name__ == "__main__":
    asyncio.run(main())
