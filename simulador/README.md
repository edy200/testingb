# Simulador BIOBUZZ

Simulador web de la cancha FTC 2026-2027 (BIOBUZZ) para probar la torreta y las rutas del robot sin prenderlo.

## Cómo abrirlo

Abre `index.html` en cualquier navegador (doble clic). No necesita instalar nada ni conexión, salvo las fuentes de Google.

## Qué hace

- Dibuja la cancha según la Field Reset Guide V26-27.1 (posiciones aproximadas) y los hives con las coordenadas de `HiveSubsystem`.
- Dibuja el robot (MAMUTSITO.step) y la torreta (HIGHTIDE TORRETA.step) vistos desde arriba.
- Usa las mismas fórmulas que el código del robot:
  - `PoseMath.turretAngleToTarget` y `Turrent.setTarget` (límites de ±170°)
  - elección del hive más cercano con histéresis (`HiveSubsystem`)
  - meta virtual de `TiroEnMovimiento`
  - tablas de `Interpolation` (misma spline que `InterpLUT` de SolversLib)
- Rutas: agrega puntos con el botón "Agregar puntos" o con Shift + clic, y copia el código para Pedro Pathing.

Si cambias una fórmula o una constante en el código Java, hay que actualizarla también en `index.html`.

## Herramientas

`herramientas/step_topview.py` lee un STEP exportado de Onshape y saca la silueta vista desde arriba de cada pieza (JSON en pulgadas). Así se generaron los dibujos del robot y la torreta.

```bash
python3 -I herramientas/step_topview.py robot.step salida.json
```
