# Supabase

La migración crea el esquema del vertical slice, activa RLS sin políticas públicas y crea el bucket privado `part2-recordings`.

Aplicación local con Supabase CLI:

```bash
supabase link --project-ref <project-ref>
supabase db push
```

El navegador no recibe la service-role key. FastAPI crea capacidades de subida y URLs de reproducción temporales; la interfaz usa únicamente la anon key pública para consumir la capacidad firmada de Storage.
