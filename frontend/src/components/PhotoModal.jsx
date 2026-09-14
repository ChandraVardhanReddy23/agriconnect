import React, { useEffect, useState } from 'react';

export function usePhotoModal() {
  const [openPhoto, setOpenPhoto] = useState(null);

  useEffect(() => {
    const handler = (event) => {
      if (event.key === 'Escape') setOpenPhoto(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const modal = openPhoto && (
    <div className="photo-modal-backdrop" onClick={() => setOpenPhoto(null)}>
      <img src={openPhoto} alt="Produce full view" className="photo-modal-image"
        onClick={(event) => event.stopPropagation()} />
      <button className="photo-modal-close" onClick={() => setOpenPhoto(null)}>✕</button>
    </div>
  );
  return { openPhoto, setOpenPhoto, modal };
}
