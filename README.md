# Bot de ofertas (Telegram, Perú)

## Arquitectura
    Tú (Telegram) <-> bot.py (long polling, sin servidor ni dominio)
                       |-- extractor.py: lee la página
                       |     1. Falabella/Sodimac/Tottus, Ripley, Juntoz; API VTEX
                       |     2. genérico: JSON-LD, Magento, microdatos, metas, lectura visual
                       |     3. respaldo: tu Chrome, para páginas hechas con JavaScript
                       |-- reglas.py: decide si avisar
                       '-- datos.py: SQLite (ofertas.db), productos e historial

Corre en tu PC: vigila solo mientras esté encendida, despierta y con internet.

## Cuándo avisa
- Baja 3% o más frente a la última referencia (configurable en `.env`).
- Llega a tu precio objetivo, o baja / aparece el precio con tarjeta de la tienda.
- Antes de avisar relee la página para confirmar. No repite el mismo aviso.
- Un "antes" tachado sin bajada real no genera aviso; se muestra al agregar el link.

## Instalar
1. Descarga el repositorio en una ruta corta (p. ej. `C:bot-ofertas`) y copia `.env.example` como `.env`.
2. En Telegram, @BotFather -> /newbot. Pega el token (nunca lo subas al repo) en `.env` (TELEGRAM_TOKEN=...).
3. Doble clic en `iniciar.bat` y abre el link que muestra, para hacerte dueño.

## Límites
Si una tienda bloquea (probado: Mercado Libre, Sercoplus) el bot lo dice y no intenta saltarlo.
Las promociones bancarias o cupones que solo salen en el carrito no se ven.
Pruebas: `python pruebas.py`
