# En parking_middleware/main.py
import uvicorn
import xmlrpc.client
import datetime
import math # NUEVO: Necesario para redondear horas
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List

# NUEVO: Importar Mercado Pago
import mercadopago

# --- Configuración Clave ---

# 1. IP de esta PC
TU_IP_LOCAL = "192.168.1.32" 

# 2. Configuración de tu Odoo
ODOO_URL = "http://127.0.0.1:8069"
ODOO_DB = "odo-park"
ODOO_USER = "agusjcr2016@gmail.com"
ODOO_PASS = "odotech2025"

# 3. NUEVO: Configuración de Mercado Pago
# ¡PEGA TU TOKEN DE PRODUCCIÓN AQUÍ!
MP_ACCESS_TOKEN = "APP_USR-457722120244315-103109-59b79bb47cf7112a3c93b7a56a06b2d3-2958197298" 
MP_PRODUCTO_NOMBRE = "Servicio de Parking" # Nombre del producto en Odoo

# --- Inicialización ---
app = FastAPI()
templates = Jinja2Templates(directory=".") 

# NUEVO: Inicializar el SDK de Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# --- Manejador de Conexiones WebSocket (La Pantalla) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# --- Lógica de Odoo ---

def get_odoo_models():
    """Conecta y devuelve el 'uid' y el 'models' para operar."""
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
        if not uid:
            print("Error: Falló la autenticación con Odoo.")
            return None, None
        
        print(f"Conectado a Odoo (UID: {uid})")
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        return uid, models
    except Exception as e:
        print(f"Error al conectar con Odoo: {e}")
        return None, None

def registrar_entrada(uid, models, patente):
    """Crea un ticket de entrada."""
    print(f"Registrando ENTRADA para: {patente}")
    domain = [('x_plate_number', '=', patente), ('x_state', '=', 'activo')]
    ticket_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'search', [domain], {'limit': 1}
    )
    
    if ticket_ids:
        print(f"Ticket activo ya existe para {patente}.")
        return {"status": "ok", "message": "Ticket ya existente"}

    ticket_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'create', [{
            'x_plate_number': patente,
            'x_start_time': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'x_state': 'activo'
        }]
    )
    print(f"Ticket de ENTRADA creado (ID: {ticket_id})")
    return {"status": "ok", "message": "Ticket de entrada creado", "id": ticket_id}


# NUEVO: Esta función reemplaza a 'registrar_salida_y_facturar'
def generar_pago_salida(uid, models, patente):
    """
    Cierra el ticket, calcula el precio y genera un link de pago de Mercado Pago.
    """
    print(f"Generando PAGO DE SALIDA (MP) para: {patente}")
    
    # 1. Buscar el ticket ACTIVO de esa patente
    domain = [('x_plate_number', '=', patente), ('x_state', '=', 'activo')]
    ticket_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'search', [domain], {'limit': 1}
    )
    
    if not ticket_ids:
        print(f"Error: No se encontró ticket activo para {patente}.")
        return None, "No se encontró ticket de entrada activo"
    
    ticket_id = ticket_ids[0]
    
    # 2. Leer la hora de inicio del ticket
    ticket_data = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'read',
        [ticket_id], {'fields': ['x_start_time']}
    )[0]
    
    start_time_str = ticket_data['x_start_time']
    start_time_naive = datetime.datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    start_time = start_time_naive.replace(tzinfo=datetime.timezone.utc) # Solución de la zona horaria
    
    # 3. Calcular duración
    hora_salida = datetime.datetime.now(datetime.timezone.utc)
    delta = hora_salida - start_time
    duracion_horas = delta.total_seconds() / 3600.0
    horas_a_cobrar = math.ceil(duracion_horas)
    if horas_a_cobrar == 0:
        horas_a_cobrar = 1
        
    print(f"Horas a cobrar: {horas_a_cobrar} (Duración: {duracion_horas:.2f}h)")

    # 4. Buscar el precio del producto en Odoo
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'product.product', 'search',
        [[('name', '=', MP_PRODUCTO_NOMBRE)]], {'limit': 1}
    )
    if not product_ids:
        return None, f"Producto '{MP_PRODUCTO_NOMBRE}' no encontrado en Odoo"
        
    product_data = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'product.product', 'read',
        [product_ids[0]], {'fields': ['list_price']}
    )[0]
    
    precio_por_hora = product_data['list_price']
    total_a_pagar = precio_por_hora * horas_a_cobrar
    
    print(f"Precio/Hora: ${precio_por_hora}. Total a Pagar: ${total_a_pagar}")

    # 5. Cerrar el ticket en Odoo
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'write',
        [ticket_id, {
            'x_end_time': hora_salida.strftime('%Y-%m-%d %H:%M:%S'),
            'x_state': 'finalizado' # Marcamos como finalizado, no facturado
        }]
    )
    print(f"Ticket {ticket_id} CERRADO en Odoo.")
    
    # 6. ¡Llamar a Mercado Pago!
    try:
        payment_data = {
            "items": [
                {
                    "title": f"Parking Patente {patente}",
                    "description": f"Estadía de {horas_a_cobrar} hora(s)",
                    "quantity": 1,
                    "unit_price": total_a_pagar
                }
            ],
            "back_urls": { # URLs a donde volver (pueden ser tu web)
                "success": "https://www.google.com",
                "failure": "https://www.google.com",
                "pending": "https://www.google.com"
            },
            "auto_return": "approved",
            "external_reference": f"TICKET-{ticket_id}-{patente}"
        }

        # CORRECCIÓN: Usamos preference() para obtener el init_point
        preference_response = sdk.preference().create(payment_data)
        
        # Verificamos errores de la API de MP
        if preference_response.get("status", 200) >= 400:
             raise Exception(f"MP Error: {preference_response['response']}")

        preference = preference_response["response"]
        
        # Esta es la URL que queremos para el QR
        url_pago_mp = preference["init_point"] 
        print(f"URL de Mercado Pago generada: {url_pago_mp}")
        
        return url_pago_mp, "Link de Mercado Pago generado"

    except Exception as e:
        # Mostramos el error detallado de MP
        print(f"Error al crear pago en Mercado Pago: {e}")
        return None, f"Error en Mercado Pago: {e}"

    """
    Cierra el ticket, calcula el precio y genera un link de pago de Mercado Pago.
    """
    print(f"Generando PAGO DE SALIDA (MP) para: {patente}")
    
    # 1. Buscar el ticket ACTIVO de esa patente
    domain = [('x_plate_number', '=', patente), ('x_state', '=', 'activo')]
    ticket_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'search', [domain], {'limit': 1}
    )
    
    if not ticket_ids:
        print(f"Error: No se encontró ticket activo para {patente}.")
        return None, "No se encontró ticket de entrada activo"
    
    ticket_id = ticket_ids[0]
    
    # 2. Leer la hora de inicio del ticket
    ticket_data = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'read',
        [ticket_id], {'fields': ['x_start_time']}
    )[0]
    
    start_time_str = ticket_data['x_start_time']
    start_time_naive = datetime.datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
    
    # -----------------------------------------------------------------
    # ¡SOLUCIÓN! Homogenizamos las zonas horarias
    # Asignamos UTC a la hora de entrada para que coincida con hora_salida
    start_time = start_time_naive.replace(tzinfo=datetime.timezone.utc)
    # -----------------------------------------------------------------

    # 3. Calcular duración
    hora_salida = datetime.datetime.now(datetime.timezone.utc)
    delta = hora_salida - start_time
    duracion_horas = delta.total_seconds() / 3600.0
    horas_a_cobrar = math.ceil(duracion_horas)
    if horas_a_cobrar == 0:
        horas_a_cobrar = 1
        
    print(f"Horas a cobrar: {horas_a_cobrar} (Duración: {duracion_horas:.2f}h)")

    # 4. Buscar el precio del producto en Odoo
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'product.product', 'search',
        [[('name', '=', MP_PRODUCTO_NOMBRE)]], {'limit': 1}
    )
    if not product_ids:
        return None, f"Producto '{MP_PRODUCTO_NOMBRE}' no encontrado en Odoo"
        
    product_data = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'product.product', 'read',
        [product_ids[0]], {'fields': ['list_price']}
    )[0]
    
    precio_por_hora = product_data['list_price']
    total_a_pagar = precio_por_hora * horas_a_cobrar
    
    print(f"Precio/Hora: ${precio_por_hora}. Total a Pagar: ${total_a_pagar}")

    # 5. Cerrar el ticket en Odoo
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, 'parking.ticket', 'write',
        [ticket_id, {
            'x_end_time': hora_salida.strftime('%Y-%m-%d %H:%M:%S'),
            'x_state': 'finalizado' # Marcamos como finalizado, no facturado
        }]
    )
    print(f"Ticket {ticket_id} CERRADO en Odoo.")
    
    # 6. ¡Llamar a Mercado Pago!
    try:
        payment_data = {
            "items": [
                {
                    "title": f"Parking Patente {patente}",
                    "description": f"Estadía de {horas_a_cobrar} hora(s)",
                    "quantity": 1,
                    "unit_price": total_a_pagar
                }
            ],
            "back_urls": { # URLs a donde volver (pueden ser tu web)
                "success": "https://www.google.com",
                "failure": "https://www.google.com",
                "pending": "https://www.google.com"
            },
            "auto_return": "approved",
            "external_reference": f"TICKET-{ticket_id}-{patente}"
        }

        # Crear la preferencia de pago
        payment_response = sdk.payment().create(payment_data)
        print(f"Respuesta Completa MP: {payment_response}")
        payment = payment_response["response"]
        
        # Esta es la URL que queremos para el QR
        url_pago_mp = payment["init_point"] 
        print(f"URL de Mercado Pago generada: {url_pago_mp}")
        
        return url_pago_mp, "Link de Mercado Pago generado"

    except Exception as e:
        print(f"Error al crear pago en Mercado Pago: {e}")
        return None, f"Error en Mercado Pago: {e}"

# --- Endpoints (URLs) del Cerebro ---

@app.get("/", response_class=HTMLResponse)
async def get_kiosk_page(request: Request):
    """ Sirve la página index.html del Kiosk/Pantalla """
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """ Maneja la conexión WebSocket de la Pantalla """
    await manager.connect(websocket)
    print("¡Pantalla de Salida CONECTADA!")
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        print("¡Pantalla de Salida DESCONECTADA!")
        manager.disconnect(websocket)

@app.post("/webhook/patente_detectada")
async def webhook_recibido(datos_ia: dict):
    """ El webhook principal que recibe la llamada de la IA """
    print(f"¡Webhook recibido! Datos: {datos_ia}")
    
    try:
        patente = datos_ia['results'][0]['plate']
        camera_id = datos_ia.get('camera_id', 'entrada') 
        
        uid, models = get_odoo_models()
        if not uid:
            return {"status": "error", "message": "No se pudo conectar a Odoo"}

        if camera_id == 'entrada':
            resultado = registrar_entrada(uid, models, patente)
        
        elif camera_id == 'salida':
            
            # --- LÓGICA MODIFICADA ---
            # 1. Llamamos a nuestra nueva función
            url_de_pago_mp, msg = generar_pago_salida(uid, models, patente)
            
            if url_de_pago_mp:
                # 2. ¡Enviamos la URL de Mercado Pago a la Pantalla!
                print(f"Enviando a pantalla (WebSocket): {url_de_pago_mp}")
                await manager.broadcast(f'{{"patente": "{patente}", "url": "{url_de_pago_mp}"}}')
                resultado = {"status": "ok", "message": msg}
            else:
                resultado = {"status": "error", "message": msg}
        
        else:
             resultado = {"status": "error", "message": "ID de cámara no reconocido"}
        
        return resultado
        
    except Exception as e:
        print(f"Error procesando el JSON: {e}")
        return {"status": "error", "message": f"Error procesando JSON: {e}"}

# --- Punto de arranque ---
if __name__ == "__main__":
    print(f"Iniciando el cerebro en http://0.0.0.0:8000")
    print(f"La pantalla (Kiosk) está en http://{TU_IP_LOCAL}:8000")
    print(f"El endpoint de la IA es http://{TU_IP_LOCAL}:8000/webhook/patente_detectada")
    uvicorn.run(app, host="0.0.0.0", port=8000)