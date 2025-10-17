import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from pdfminer.high_level import extract_text
import smtplib
from email.mime.text import MIMEText
import tempfile
import os
import requests
from urllib.parse import urljoin


async def obtener_url_ultimo_boletin():
    """Abre la página del BOJA y extrae la URL del botón 'Acceder al último BOJA' que está dentro del Shadow DOM."""
    url = "https://www.juntadeandalucia.es/boja/"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        # Esperar al componente personalizado y acceder al shadow DOM
        shadow_host = await page.query_selector("matter-last-boja")
        shadow_root = await shadow_host.evaluate_handle("el => el.shadowRoot")
        enlace = await shadow_root.query_selector("a[aria-label*='ACCEDER AL ÚLTIMO BOJA']")
        href = await enlace.get_attribute("href")

        await browser.close()

        if not href.startswith("http"):
            href = "https://www.juntadeandalucia.es" + href
        return href


def obtener_enlace_sumario(url_boletin):
    """Obtiene el enlace al 'Sumario del boletín' (PDF). Devuelve URL absoluta o None."""
    try:
        r = requests.get(url_boletin, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Error al descargar la página del boletín: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # 1) Buscar por atributo title que contenga 'sumario'
    a = soup.find("a", attrs={"title": lambda x: x and "sumario" in x.lower()})
    if not a:
        # 2) Buscar por texto visible que contenga 'sumario boletín' (o variantes)
        a = soup.find("a", string=lambda s: s and "sumario" in s.lower())

    if not a:
        # 3) Buscar cualquier enlace a .pdf que tenga 'sumario' en el href
        pdf_links = soup.find_all("a", href=lambda h: h and h.lower().endswith(".pdf"))
        for link in pdf_links:
            href = link.get("href", "")
            if "sumario" in href.lower():
                a = link
                break

    if not a:
        # 4) Como último recurso, revisar los .pdf y ver si el texto del padre contiene 'sumario'
        for link in pdf_links:
            parent = link.find_parent()
            parent_text = parent.get_text(separator=" ").lower() if parent else ""
            if "sumario" in parent_text:
                a = link
                break

    if not a:
        print("❌ No se encontró el enlace al sumario en la página del boletín.")
        return None

    href = a.get("href")
    if not href:
        print("❌ El enlace encontrado no tiene href.")
        return None

    # Convertir a URL absoluta (maneja href relativos como "BOJA25-196-...pdf")
    url_sumario = urljoin(url_boletin, href)
    return url_sumario


def descargar_y_extraer_pdf(url_pdf):
    """Descarga el PDF del sumario y extrae su texto."""
    r = requests.get(url_pdf)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(r.content)
        tmp_path = tmp.name
    texto = extract_text(tmp_path)
    return texto

def buscar_frase(texto):
    """Busca la frase objetivo con comparación aproximada."""
    objetivo = "Subvenciones en régimen de concurrencia no competitiva a organizaciones sindicales para la financiación de gastos corrientes"
    similitud = fuzz.partial_ratio(objetivo.lower(), texto.lower())
    return similitud

def enviar_correo(similitud):
    """Envía un correo si la frase se encuentra con alta similitud."""
    remitente = os.getenv("EMAIL_USER")
    contraseña = os.getenv("EMAIL_PASS")
    destinatario = os.getenv("EMAIL_DEST")

    msg = MIMEText(f"Se ha encontrado la frase con una similitud del {similitud}%.")
    msg["Subject"] = "Aviso BOJA"
    msg["From"] = remitente
    msg["To"] = destinatario

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(remitente, contraseña)
        server.send_message(msg)

async def main():
    print("🔍 Buscando último BOJA...")
    url_boletin = await obtener_url_ultimo_boletin()
    if not url_boletin:
        print("❌ No se encontró el último BOJA.")
        return

    print(f"➡️ Último boletín: {url_boletin}")
    url_sumario = obtener_enlace_sumario(url_boletin)
    if not url_sumario:
        return

    print(f"📄 Descargando sumario: {url_sumario}")
    texto = descargar_y_extraer_pdf(url_sumario)

    print("🧠 Analizando contenido del boletín...")
    similitud = buscar_frase(texto)
    print(f"Similitud encontrada: {similitud}%")

    if similitud >= 80:
        print("✅ Frase encontrada, enviando correo...")
        enviar_correo(similitud)
    else:
        print("⚠️ No se encontró la frase con suficiente similitud.")

if __name__ == "__main__":
    asyncio.run(main())
