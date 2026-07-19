# Perfiles de voz británica

Este archivo documenta candidatos y criterios de selección. Las variables de entorno no activan por sí solas ningún proveedor y no demuestran que una voz esté disponible en una cuenta concreta. Mientras `*_VOICE_PROFILE_VERIFIED=false`, el perfil debe considerarse propuesto, no validado.

## Voz del examinador

Uso recomendado: instrucciones estables pre-generadas, no síntesis en cada sesión.

- Proveedor candidato: Azure Speech.
- Locale: `en-GB`.
- Primera candidata: `en-GB-SoniaNeural`.
- Alternativas para una prueba ciega: `en-GB-LibbyNeural` y `en-GB-RyanNeural`.

La elección final debe hacerse con una prueba ciega entre profesores y alumnos sobre claridad, naturalidad, neutralidad, ritmo y ausencia de un tono inquietante. Conviene generar los audios una vez, revisarlos y versionarlos con el contenido de la práctica.

## Voz del candidato IA experimental

Uso recomendado: voz conversacional en tiempo real, solo cuando exista el modo de candidato IA.

- Primera opción técnica a comparar: OpenAI Realtime con `marin` y `cedar`.
- Alternativa: Azure Voice Live con una voz `en-GB` elegida en la misma prueba ciega.

Los nombres `marin` y `cedar` no constituyen una garantía contractual de acento británico. Deben comprobarse con las credenciales y la versión del proveedor realmente desplegadas. El perfil del candidato también necesitará control de turnos, silencios y longitud para no dominar la conversación; elegir una voz agradable no resuelve ese comportamiento.

## Criterio de verificación

Solo cambiar `EXAMINER_VOICE_PROFILE_VERIFIED` o `AI_PARTNER_VOICE_PROFILE_VERIFIED` a `true` cuando se hayan completado ambos pasos:

1. Comprobación de disponibilidad con las credenciales de producción o del entorno de prueba.
2. Prueba ciega aprobada con las muestras y el texto propios de la academia.

No se deben copiar, descargar, clonar ni imitar grabaciones de Cambridge. El objetivo es una voz británica clara y apropiada para práctica, no reproducir la identidad vocal de sus materiales.
