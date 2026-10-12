import React, { useState, useEffect } from 'react';

export default function App() {
  const [preguntas, setPreguntas] = useState([]);
  const [respuestas, setRespuestas] = useState({});
  const [anoEscolar, setAnoEscolar] = useState(2026);
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState('');
  const [cargando, setCargando] = useState(true);


// Función para auto-llenar el formulario de prueba con un clic
const handleAutoFill = () => {
  const respuestasSimuladas = {};
  
  preguntas.forEach((p) => {
    if (p.seccion_test === 'capacidades') {
      // Asigna valores del 1 al 7 diferentes para evitar la regla de todas iguales
      respuestasSimuladas[p.id_pregunta] = String((p.id_pregunta % 7) + 1);
    } else {
      // Asigna 'S' o 'N' de forma aleatoria
      respuestasSimuladas[p.id_pregunta] = Math.random() > 0.5 ? 'S' : 'N';
    }
  });

  setRespuestas(respuestasSimuladas);
};

  // 1. Cargar preguntas desde GET /preguntas
  useEffect(() => {
    fetch('http://127.0.0.1:8000/preguntas')
      .then((res) => res.json())
      .then((response) => {
        if (response.status === 'success') {
          setPreguntas(response.data);
        } else {
          setError('Error de base de datos: ' + response.detalle);
        }
        setCargando(false);
      })
      .catch((err) => {
        console.error('Error de conexión:', err);
        setError('No se pudo conectar con la API de FastAPI. ¿Está corriendo uvicorn?');
        setCargando(false);
      });
  }, []);

  // 2. Guardar respuesta seleccionada
  const handleOptionChange = (idPregunta, valor) => {
    setRespuestas({
      ...respuestas,
      [idPregunta]: valor,
    });
  };

  // 3. Enviar a POST /guardar_respuestas
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    // Validar que en 'capacidades' no seleccionen exactamente lo mismo en todas
    const preguntasCapacidades = preguntas.filter(p => p.seccion_test === 'capacidades');
    if (preguntasCapacidades.length > 0) {
      const respuestasCap = preguntasCapacidades.map(p => respuestas[p.id_pregunta]);
      const primerValor = respuestasCap[0];
      const todasIguales = respuestasCap.every(v => v !== undefined && v === primerValor);
      
      if (todasIguales && respuestasCap.length === preguntasCapacidades.length) {
        setError('En la sección "Califica tus capacidades" debes variar tus puntuaciones, no puedes calificar todas por igual.');
        return;
      }
    }

    // Construir el payload según el modelo EvaluacionEstudiante de Pydantic
    const payload = {
      id_usuario: 1, // ID de prueba
      ano_escolar: parseInt(anoEscolar, 10),
      respuestas: Object.keys(respuestas).map((idStr) => {
        const id = parseInt(idStr, 10);
        const preg = preguntas.find((p) => p.id_pregunta === id);
        return {
          id_pregunta: id,
          seccion_test: preg ? preg.seccion_test : 'actividades',
          respuesta: String(respuestas[idStr]), // Se envía como texto según tu modelo
        };
      }),
    };

    try {
      const res = await fetch('http://127.0.0.1:8000/guardar_respuestas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      setResultado(data);
    } catch (err) {
      console.error('Error al enviar:', err);
      setError('Error al enviar la evaluación al servidor.');
    }
  };

  if (cargando) {
    return <div style={{ padding: '40px', textAlign: 'center' }}>Cargando banco de preguntas desde MySQL...</div>;
  }

  return (
    <div style={{ padding: '30px', maxWidth: '850px', margin: '0 auto', fontFamily: 'Segoe UI, sans-serif' }}>
      <h2>Prueba de Integración: Sistema de Orientación Vocacional SDS</h2>
      <p>Preguntas en base de datos: <strong>{preguntas.length}</strong></p>
      
      <div style={{ marginBottom: '20px' }}>
        <label><strong>Año escolar / Período: </strong></label>
        <input 
          type="number" 
          value={anoEscolar} 
          onChange={(e) => setAnoEscolar(e.target.value)}
          style={{ padding: '5px', width: '80px' }}
        />
      </div>
      <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
  <button 
    type="button" 
    onClick={handleAutoFill}
    style={{ padding: '10px 15px', backgroundColor: '#6c757d', color: '#fff', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
  >
    ⚡ Llenar Formulario Automáticamente (Prueba)
  </button>

  <button 
    type="submit" 
    style={{ padding: '10px 20px', backgroundColor: '#007bff', color: '#fff', border: 'none', borderRadius: '5px', cursor: 'pointer' }}
  >
    Guardar Evaluación en Base de Datos
  </button>
</div>
      <hr />

      {error && (
        <div style={{ padding: '12px', backgroundColor: '#f8d7da', color: '#721c24', border: '1px solid #f5c6cb', borderRadius: '5px', marginBottom: '20px' }}>
          <strong>Atención:</strong> {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {preguntas.map((p) => (
          <div key={p.id_pregunta} style={{ borderBottom: '1px solid #eee', padding: '12px 0' }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '15px' }}>
              <span style={{ 
                backgroundColor: p.seccion_test === 'capacidades' ? '#28a745' : '#007bff', 
                color: '#fff', 
                padding: '3px 7px', 
                borderRadius: '4px', 
                fontSize: '11px',
                fontWeight: 'bold',
                textTransform: 'uppercase'
              }}>
                {p.seccion_test}
              </span>{' '}
              {p.texto_pregunta}
            </p>

            {p.seccion_test === 'capacidades' ? (
              /* Selector escalar (1 al 7) para capacidades */
              <div>
                <label style={{ fontSize: '14px', color: '#555' }}>Autoevaluación (1-Baja a 7-Alta): </label>
                <select 
                  value={respuestas[p.id_pregunta] || '4'} 
                  onChange={(e) => handleOptionChange(p.id_pregunta, e.target.value)}
                  style={{ padding: '4px 8px', borderRadius: '4px' }}
                >
                  {[1, 2, 3, 4, 5, 6, 7].map((num) => (
                    <option key={num} value={String(num)}>{num}</option>
                  ))}
                </select>
              </div>
            ) : (
              /* Selección S / N para las demás secciones */
              <div>
                <label style={{ marginRight: '20px', cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name={`pregunta_${p.id_pregunta}`}
                    value="S"
                    checked={respuestas[p.id_pregunta] === 'S'}
                    onChange={(e) => handleOptionChange(p.id_pregunta, e.target.value)}
                  /> Sí (S)
                </label>
                <label style={{ cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name={`pregunta_${p.id_pregunta}`}
                    value="N"
                    checked={respuestas[p.id_pregunta] === 'N'}
                    onChange={(e) => handleOptionChange(p.id_pregunta, e.target.value)}
                  /> No (N)
                </label>
              </div>
            )}
          </div>
        ))}

        <button 
          type="submit" 
          style={{ 
            marginTop: '25px', 
            padding: '12px 24px', 
            backgroundColor: '#007bff', 
            color: '#fff', 
            border: 'none', 
            borderRadius: '5px', 
            fontSize: '16px', 
            cursor: 'pointer' 
          }}
        >
          Guardar Evaluación en Base de Datos
        </button>
      </form>

      {/* Resultado de la respuesta de FastAPI */}
      {resultado && (
        <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#d4edda', border: '1px solid #c3e6cb', color: '#155724', borderRadius: '5px' }}>
          <h3>¡Respuesta del Servidor!</h3>
          <pre style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '4px', overflowX: 'auto' }}>
            {JSON.stringify(resultado, null, 2)}
          </pre>
        </div>
      )}
    </div>

    
  );
}