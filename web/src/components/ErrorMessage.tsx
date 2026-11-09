// The server's message for a failed request, announced to screen readers.
export function ErrorMessage({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p className="error" role="alert">
      {error}
    </p>
  )
}
