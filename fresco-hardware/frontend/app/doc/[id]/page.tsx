/**
 * Document detail page — three-pane extraction review UI.
 *
 * Panes:
 *   Left:   PDF viewer with bounding box overlays for selected set
 *   Center: List of extracted hardware sets with confidence indicators
 *   Right:  Component detail table with inline editing for corrections
 */

export default function DocumentPage({ params }: { params: { id: string } }) {
  return (
    <main>
      <h1>Document {params.id}</h1>
      {/* TODO: three-pane layout */}
    </main>
  );
}
