from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from pydantic import BaseModel
from typing import List
import json
from decimal import Decimal

app = FastAPI(
    title="API Sistema Orientación Vocacional SDS",
    description="Backend ajustado: cálculo directo de puntuación y porcentaje por categoría RIASEC."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def obtener_conexion():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="orientacion_vocacional"
    )

# Models Pydantic
class RespuestaItem(BaseModel):
    id_pregunta: int
    seccion_test: str
    respuesta: str  # 'S' / 'N' o '1' / '0'

class EvaluacionEstudiante(BaseModel):
    id_usuario: int
    ano_escolar: int
    respuestas: List[RespuestaItem]

class LoginRequest(BaseModel):
    correo: str
    contrasena: str


# --- RUTAS DE LA API ---

@app.get("/")
def inicio():
    return {"status": "ok", "mensaje": "API Vocacional activa y lista"}

@app.get("/usuarios")
def obtener_usuarios():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        cursor.execute("SELECT id_usuario, nombre, correo, rol FROM usuarios")
        lista_usuarios = cursor.fetchall()
        cursor.close()
        conexion.close()
        return {"status": "success", "total": len(lista_usuarios), "data": lista_usuarios}
    except Exception as e:
        return {"status": "error", "detalle": str(e)}

@app.get("/preguntas")
def obtener_preguntas():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        sql = """
            SELECT p.id_pregunta, p.texto_pregunta, p.seccion_test, p.id_categoria, c.codigo, c.nombre AS categoria_nombre
            FROM preguntas p
            INNER JOIN categorias_riasec c ON p.id_categoria = c.id_categoria
        """
        cursor.execute(sql)
        data = cursor.fetchall()
        cursor.close()
        conexion.close()
        return {"status": "success", "total": len(data), "data": data}
    except Exception as e:
        return {"status": "error", "detalle": str(e)}


# ---------------------------------------------------------------------------
# ENDPOINT PRINCIPAL: Procesa las respuestas, calcula puntuación y porcentaje
# y registra directamente en 'resultado' y 'resultado_por_categoria'
# ---------------------------------------------------------------------------
@app.post("/guardar_respuestas")
def guardar_respuestas(evaluacion: EvaluacionEstudiante):
    conexion = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)

        # 1. Obtener a qué categoría pertenece cada pregunta enviada
        ids_preguntas = [r.id_pregunta for r in evaluacion.respuestas]
        if not ids_preguntas:
            raise HTTPException(status_code=400, detail="No se enviaron respuestas")

        format_strings = ','.join(['%s'] * len(ids_preguntas))
        cursor.execute(
            f"SELECT id_pregunta, id_categoria FROM preguntas WHERE id_pregunta IN ({format_strings})",
            tuple(ids_preguntas)
        )
        mapa_preguntas = {row['id_pregunta']: row['id_categoria'] for row in cursor.fetchall()}

        # 2. Consultar todas las categorías RIASEC registradas
        cursor.execute("SELECT id_categoria, codigo, nombre FROM categorias_riasec")
        categorias = cursor.fetchall()
        
        # Inicializar estructuras para conteo de puntos y total de preguntas por categoría
        puntuacion_categoria = {c['id_categoria']: 0 for c in categorias}
        total_preguntas_categoria = {c['id_categoria']: 0 for c in categorias}
        codigo_categoria = {c['id_categoria']: c['codigo'] for c in categorias}

        # 3. Sumar respuestas afirmativas
        for r in evaluacion.respuestas:
            cat_id = mapa_preguntas.get(r.id_pregunta)
            if cat_id:
                total_preguntas_categoria[cat_id] += 1
                val = str(r.respuesta).strip().upper()
                if val in ['S', '1', 'TRUE']:
                    puntuacion_categoria[cat_id] += 1

        # 4. Crear el registro en la tabla 'test'
        cursor.execute(
            "INSERT INTO test (id_usuario, ano_escolar, estado_test) VALUES (%s, %s, 'completado')",
            (evaluacion.id_usuario, evaluacion.ano_escolar)
        )
        id_test_creado = cursor.lastrowid

        # 5. Generar el Código Holland (Top 3 categorías con mayor puntuación)
        ordenados = sorted(puntuacion_categoria.items(), key=lambda x: x[1], reverse=True)
        codigo_holland = "".join([codigo_categoria[cat_id] for cat_id, _ in ordenados[:3]])

        # Crear diccionario para almacenar en la columna JSON 'puntaje_detallado' de la tabla 'resultado'
        puntaje_detallado_json = {codigo_categoria[c_id]: puntuacion_categoria[c_id] for c_id in puntuacion_categoria}

        # 6. Insertar en la tabla 'resultado'
        cursor.execute(
            """
            INSERT INTO resultado (id_test, id_usuario, codigo_holland, puntaje_detallado)
            VALUES (%s, %s, %s, %s)
            """,
            (id_test_creado, evaluacion.id_usuario, codigo_holland, json.dumps(puntaje_detallado_json))
        )
        id_resultado_creado = cursor.lastrowid

        # 7. Insertar desglose en 'resultado_por_categoria' (Puntuación total y Porcentaje)
        registros_categoria = []
        for cat_id, puntos in puntuacion_categoria.items():
            max_posible = total_preguntas_categoria[cat_id]
            # Cálculo del porcentaje (relativo al total de preguntas de la categoría)
            porcentaje = round((puntos / max_posible * 100), 2) if max_posible > 0 else 0.00
            
            registros_categoria.append((id_resultado_creado, cat_id, puntos, porcentaje))

        cursor.executemany(
            """
            INSERT INTO resultado_por_categoria (id_resultado, id_categoria, puntuacion_total, porcentaje)
            VALUES (%s, %s, %s, %s)
            """,
            registros_categoria
        )

        conexion.commit()

        return {
            "status": "success",
            "mensaje": "Test procesado y guardado correctamente en resultado_por_categoria",
            "id_test": id_test_creado,
            "id_resultado": id_resultado_creado,
            "codigo_holland": codigo_holland,
            "resumen_puntuaciones": puntaje_detallado_json
        }

    except mysql.connector.Error as err:
        if conexion:
            conexion.rollback()
        return {"status": "error", "detalle": f"{err.errno} ({err.sqlstate}): {err.msg}"}
    finally:
        if conexion and conexion.is_connected():
            cursor.close()
            conexion.close()


# ---------------------------------------------------------------------------
# ENDPOINT DE CONSULTA: Obtiene los porcentajes y puntuaciones directamente
# de 'resultado_por_categoria'
# ---------------------------------------------------------------------------
@app.get("/api/resultado/{id_test}")
def obtener_resultado_vocacional(id_test: int):
    conexion = None
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)

        # 1. Obtener la cabecera del resultado
        cursor.execute(
            "SELECT id_resultado, id_usuario, codigo_holland, puntaje_detallado FROM resultado WHERE id_test = %s",
            (id_test,)
        )
        resultado = cursor.fetchone()

        if not resultado:
            return {"status": "error", "mensaje": f"No existe un resultado registrado para el id_test: {id_test}"}

        # Parsear puntaje_detallado si viene como string JSON
        puntaje_json = resultado.get("puntaje_detallado")
        if isinstance(puntaje_json, str):
            try:
                puntaje_json = json.loads(puntaje_json)
            except Exception:
                puntaje_json = {}

        # 2. Consultar los porcentajes y puntuaciones por categoría
        sql_por_categoria = """
            SELECT 
                rc.id_resultadoCategoria,
                rc.id_categoria,
                c.codigo,
                c.nombre AS nombre_categoria,
                rc.puntuacion_total,
                rc.porcentaje
            FROM resultado_por_categoria rc
            INNER JOIN categorias_riasec c ON rc.id_categoria = c.id_categoria
            WHERE rc.id_resultado = %s
            ORDER BY rc.puntuacion_total DESC
        """
        cursor.execute(sql_por_categoria, (resultado["id_resultado"],))
        desglose_categorias = cursor.fetchall()

        # Convertir valores Decimal a float/int para evitar error de serialización JSON en FastAPI
        for cat in desglose_categorias:
            if isinstance(cat.get("porcentaje"), Decimal):
                cat["porcentaje"] = float(cat["porcentaje"])

        # 3. Consultar carreras sugeridas tomando la categoría principal
        codigo_holland = resultado.get("codigo_holland") or ""
        letra_principal = codigo_holland[0] if len(codigo_holland) > 0 else ""

        carreras_sugeridas = []
        if letra_principal:
            cursor.execute(
                """
                SELECT car.id_carrera, car.nombre_carrera, car.reticula
                FROM carreras car
                INNER JOIN categorias_riasec cat ON car.id_categoria_principal = cat.id_categoria
                WHERE cat.codigo = %s
                """,
                (letra_principal,)
            )
            carreras_sugeridas = cursor.fetchall()

        return {
            "status": "success",
            "id_test": id_test,
            "id_resultado": resultado["id_resultado"],
            "codigo_holland": codigo_holland,
            "puntaje_detallado": puntaje_json,
            "resultado_por_categoria": desglose_categorias,
            "carreras_sugeridas": carreras_sugeridas
        }

    except Exception as e:
        return {"status": "error", "detalle": str(e)}
        
    finally:
        if conexion and conexion.is_connected():
            cursor.close()
            conexion.close()

@app.post("/api/login_prueba")
def iniciar_sesion_prueba(credenciales: LoginRequest):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor(dictionary=True)
        
        sql = "SELECT id_usuario, nombre, correo, rol FROM usuarios WHERE correo = %s AND contrasena = %s"
        cursor.execute(sql, (credenciales.correo, credenciales.contrasena))
        usuario = cursor.fetchone()
        
        cursor.close()
        conexion.close()
        
        if not usuario:
            return {
                "status": "error",
                "codigo_http": 401,
                "mensaje": "Acceso denegado: Credenciales incorrectas o usuario no registrado"
            }
        
        rol_usuario = usuario["rol"]
        permisos = {
            "estudiante": ["responder_test", "ver_resultados_propios"],
            "administrador": ["gestion_total", "crud_usuarios", "crud_carreras"],
            "auxiliar": ["auditoria_reportes", "consulta_global"],
            "visitante": ["lectura_restringida"]
        }

        return {
            "status": "success",
            "mensaje": f"Sesión iniciada exitosamente con rol de: {rol_usuario}",
            "datos_usuario": usuario,
            "permisos_activos": permisos.get(rol_usuario, [])
        }

    except Exception as e:
        return {"status": "error", "detalle": str(e)}