import { useCallback, useMemo } from "react";
import {
  AssetRecordType,
  DefaultActionsMenu,
  DefaultQuickActions,
  Tldraw,
  type Editor,
  type TLComponents,
} from "tldraw";
import "tldraw/tldraw.css";
import type { CanvasMedia } from "../types";

type MediaCanvasProps = {
  mediaItems: CanvasMedia[];
};

function CustomActionsMenu() {
  return (
    <div className="tl-custom-actions">
      <DefaultActionsMenu />
    </div>
  );
}

function CustomQuickActions() {
  return (
    <div className="tl-custom-quick-actions">
      <DefaultQuickActions />
    </div>
  );
}

const TL_DRAW_COMPONENTS: TLComponents = {
  ActionsMenu: CustomActionsMenu,
  QuickActions: CustomQuickActions,
};

const tldrawLicenseKey = import.meta.env.VITE_TLDRAW_LICENSE_KEY || undefined;

export default function MediaCanvas({ mediaItems }: MediaCanvasProps) {
  const contentKey = useMemo(() => {
    if (mediaItems.length === 0) return "empty";
    return mediaItems
      .map((item, index) => `${index}:${item.id}:${item.src.length}:${item.src.slice(0, 24)}:${item.src.slice(-24)}`)
      .join("|");
  }, [mediaItems]);

  const handleMount = useCallback(
    (editor: Editor) => {
      if (mediaItems.length === 0) return;

      mediaItems.forEach((item, index) => {
        const dataUrl = normalizeMediaSource(item.src);
        const isVideo = dataUrl.startsWith("data:video");
        const assetId = AssetRecordType.createId();
        const mimeType = isVideo ? "video/mp4" : "image/png";

        if (isVideo) {
          const video = document.createElement("video");
          video.src = dataUrl;
          video.onloadedmetadata = () => {
            const display = fitDimensions(video.videoWidth || 640, video.videoHeight || 360);
            const position = calculatePosition(index, display.w, display.h);
            editor.createAssets([
              {
                id: assetId,
                type: "video",
                typeName: "asset",
                props: {
                  name: item.name,
                  src: dataUrl,
                  w: display.w,
                  h: display.h,
                  mimeType,
                  isAnimated: true,
                },
                meta: {},
              },
            ]);
            editor.createShape({
              type: "video",
              x: position.x,
              y: position.y,
              props: {
                assetId,
                w: display.w,
                h: display.h,
              },
            });
            zoomToFitSoon(editor);
          };
          return;
        }

        const image = new Image();
        image.src = dataUrl;
        image.onload = () => {
          const display = fitDimensions(image.width || 512, image.height || 512);
          const position = calculatePosition(index, display.w, display.h);
          editor.createAssets([
            {
              id: assetId,
              type: "image",
              typeName: "asset",
              props: {
                name: item.name,
                src: dataUrl,
                w: display.w,
                h: display.h,
                mimeType,
                isAnimated: false,
              },
              meta: {},
            },
          ]);
          editor.createShape({
            type: "image",
            x: position.x,
            y: position.y,
            props: {
              assetId,
              w: display.w,
              h: display.h,
            },
          });
          zoomToFitSoon(editor);
        };
      });
    },
    [mediaItems],
  );

  return (
    <div className="media-canvas" data-testid="tldraw-canvas">
      <Tldraw
        key={contentKey}
        onMount={handleMount}
        components={TL_DRAW_COMPONENTS}
        forceMobile
        licenseKey={tldrawLicenseKey}
      />
      {mediaItems.length === 0 && (
        <div className="canvas-empty">
          <div className="empty-state">
            <strong>Canvas ready for generated media</strong>
            <span>Images and videos will appear here as draggable tldraw objects.</span>
          </div>
        </div>
      )}
    </div>
  );
}

function normalizeMediaSource(value: string): string {
  if (!value) return "";
  if (value.startsWith("data:")) return value;
  return `data:image/png;base64,${value}`;
}

function fitDimensions(width: number, height: number): { w: number; h: number } {
  const maxWidth = 620;
  const maxHeight = 480;
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  return {
    w: Math.max(80, Math.round(width * scale)),
    h: Math.max(80, Math.round(height * scale)),
  };
}

function calculatePosition(index: number, width: number, height: number): { x: number; y: number } {
  const column = index % 3;
  const row = Math.floor(index / 3);
  return {
    x: 80 + column * (width + 20),
    y: 70 + row * (height + 20),
  };
}

function zoomToFitSoon(editor: Editor) {
  window.setTimeout(() => {
    editor.zoomToFit();
  }, 100);
}
