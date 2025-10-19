import asyncio
import os
import tempfile
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text
from playwright.async_api import async_playwright

OUTPUT_FILE = "sumario.txt"

async def obtener_url_ultimo_boletin():
    """Obtiene la URL del último boletín desde la página del BOJA usando Playwright."""
    url = "https://www.juntadeandalucia.es/boja/"
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
        return href

def obtener_enlace_sumario(url_boletin):
    """Extrae la URL del PDF del sumario del boletín."""
    r = requests.get(url_boletin, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    a = soup.find("a", title=lambda x: x and "sumario" in x.lower())
    if not a:
        pdf_links = soup.find_all("a", href=lambda h: h and h.lower().endswith(".pdf"))
        for link in pdf_links:
            href = link.get("href", "")
            if "sumario" in href.lower():
                a = link
                break
    if not a:
        return None
    href = a.get("href")
    if not href.startswith("http"):
        href = urljoin(url_boletin, href)
    return href

def descargar_y_extraer_pdf(url_pdf):
    """Descarga el PDF y extrae el texto."""
    r = requests.get(url_pdf)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(r.content)
        tmp_path = tmp.name
    texto = extract_text(tmp_path)
    return texto

async def main():
    try:
        url_boletin = await obtener_url_ultimo_boletin()
        if not url_boletin:
            print("❌ No se encontró el último boletín")
            return
        url_sumario = obtener_enlace_sumario(url_boletin)
        if not url_sumario:
            print("❌ No se encontró el sumario")
            return
        texto = descargar_y_extraer_pdf(url_sumario)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f"✅ Sumario guardado en {OUTPUT_FILE}")
    except Exception as e:
        print("❌ Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
