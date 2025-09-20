from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# Configuración de la base de datos
DB_CONFIG = {
    'host': 'talquin.bloom.host',
    'database': 's85166_votaciones',
    'user': 'u85166_Gvvho8waXy',
    'password': 'Zr7PIYgRMMcJtdKxXAPm2CaU'
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error conectando a MySQL: {e}")
        return None

def validate_required_fields(data, required_fields):
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    return missing_fields

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        # Validar campos requeridos
        required_fields = ['codigo_universitario', 'clave']
        missing_fields = validate_required_fields(data, required_fields)
        
        if missing_fields:
            return jsonify({
                'success': False,
                'message': f'Campos requeridos faltantes: {", ".join(missing_fields)}'
            }), 400
        
        codigo = data['codigo_universitario'].strip()
        clave = data['clave'].strip()
        
        # Validar formato del código universitario
        if len(codigo) != 12 or not codigo.isdigit():
            return jsonify({
                'success': False,
                'message': 'Código universitario debe tener 12 dígitos'
            }), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({
                'success': False,
                'message': 'Error de conexión a la base de datos'
            }), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Buscar alumno por código universitario
        query = """
        SELECT id, codigo_universitario, clave, nombres, apellidos, 
               estado_matricula, ha_votado 
        FROM alumnos 
        WHERE codigo_universitario = %s
        """
        cursor.execute(query, (codigo,))
        alumno = cursor.fetchone()
        
        if not alumno:
            return jsonify({
                'success': False,
                'message': 'Código universitario no encontrado'
            }), 401
        
        # Verificar contraseña
        if alumno['clave'] != clave:
            return jsonify({
                'success': False,
                'message': 'Contraseña incorrecta'
            }), 401
        
        # Verificar estado de matrícula
        if alumno['estado_matricula'] != 'matriculado':
            return jsonify({
                'success': False,
                'message': 'Estudiante no matriculado, no puede votar'
            }), 403
        
        # Verificar si ya votó
        if alumno['ha_votado']:
            return jsonify({
                'success': False,
                'message': 'Ya se registró su voto',
                'ya_voto': True
            }), 403
        
        return jsonify({
            'success': True,
            'message': 'Login exitoso',
            'alumno': {
                'id': alumno['id'],
                'codigo': alumno['codigo_universitario'],
                'nombres': alumno['nombres'],
                'apellidos': alumno['apellidos']
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }), 500
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/partidos', methods=['GET'])
def get_partidos():
    """Obtiene la lista de partidos políticos activos"""
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({
                'success': False,
                'message': 'Error de conexión a la base de datos'
            }), 500
        
        cursor = connection.cursor(dictionary=True)
        
        query = """
        SELECT id, nombre, representante, descripcion, ruta_imagen
        FROM partidos_politicos 
        WHERE estado = 'activo'
        ORDER BY nombre
        """
        cursor.execute(query)
        partidos = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'partidos': partidos
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }), 500
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/votar', methods=['POST'])
def votar():
    """Registra el voto de un estudiante"""
    try:
        data = request.get_json()
        
        # Validar campos requeridos
        required_fields = ['alumno_id', 'partido_id']
        missing_fields = validate_required_fields(data, required_fields)
        
        if missing_fields:
            return jsonify({
                'success': False,
                'message': f'Campos requeridos faltantes: {", ".join(missing_fields)}'
            }), 400
        
        alumno_id = data['alumno_id']
        partido_id = data['partido_id']
        ip_voto = request.remote_addr
        dispositivo = request.headers.get('User-Agent', 'Desconocido')
        
        connection = get_db_connection()
        if not connection:
            return jsonify({
                'success': False,
                'message': 'Error de conexión a la base de datos'
            }), 500
        
        cursor = connection.cursor(dictionary=True)
        
        # Verificar que el alumno existe y no ha votado
        query_alumno = """
        SELECT id, ha_votado, estado_matricula 
        FROM alumnos 
        WHERE id = %s
        """
        cursor.execute(query_alumno, (alumno_id,))
        alumno = cursor.fetchone()
        
        if not alumno:
            return jsonify({
                'success': False,
                'message': 'Estudiante no encontrado'
            }), 404
        
        if alumno['ha_votado']:
            return jsonify({
                'success': False,
                'message': 'Ya se registró su voto'
            }), 403
        
        if alumno['estado_matricula'] != 'matriculado':
            return jsonify({
                'success': False,
                'message': 'Estudiante no matriculado'
            }), 403
        
        # Verificar que el partido existe y está activo
        query_partido = """
        SELECT id, nombre 
        FROM partidos_politicos 
        WHERE id = %s AND estado = 'activo'
        """
        cursor.execute(query_partido, (partido_id,))
        partido = cursor.fetchone()
        
        if not partido:
            return jsonify({
                'success': False,
                'message': 'Partido político no válido'
            }), 404
        
        # Iniciar transacción
        connection.start_transaction()
        
        try:
            # Registrar el voto
            query_voto = """
            INSERT INTO votos (alumno_id, partido_id, fecha_voto, ip_voto, dispositivo)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(query_voto, (
                alumno_id, 
                partido_id, 
                datetime.now(), 
                ip_voto, 
                dispositivo
            ))
            
            # Marcar al alumno como que ya votó
            query_update = """
            UPDATE alumnos 
            SET ha_votado = 1, fecha_actualizacion = %s 
            WHERE id = %s
            """
            cursor.execute(query_update, (datetime.now(), alumno_id))
            
            # Confirmar transacción
            connection.commit()
            
            return jsonify({
                'success': True,
                'message': f'Voto registrado exitosamente para {partido["nombre"]}'
            }), 200
            
        except Exception as e:
            # Revertir transacción en caso de error
            connection.rollback()
            return jsonify({
                'success': False,
                'message': f'Error al registrar el voto: {str(e)}'
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }), 500
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/verificar-voto/<int:alumno_id>', methods=['GET'])
def verificar_voto(alumno_id):
    """Verifica si un alumno ya votó"""
    try:
        connection = get_db_connection()
        if not connection:
            return jsonify({
                'success': False,
                'message': 'Error de conexión a la base de datos'
            }), 500
        
        cursor = connection.cursor(dictionary=True)
        
        query = """
        SELECT ha_votado 
        FROM alumnos 
        WHERE id = %s
        """
        cursor.execute(query, (alumno_id,))
        alumno = cursor.fetchone()
        
        if not alumno:
            return jsonify({
                'success': False,
                'message': 'Estudiante no encontrado'
            }), 404
        
        return jsonify({
            'success': True,
            'ha_votado': bool(alumno['ha_votado'])
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error interno del servidor: {str(e)}'
        }), 500
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': 'Endpoint no encontrado'
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        'success': False,
        'message': 'Método no permitido'
    }), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': 'Error interno del servidor'
    }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)