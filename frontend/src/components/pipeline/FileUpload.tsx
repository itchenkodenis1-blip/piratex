import { useCallback, useRef, useState } from "react";
import {
  presignPipelineAsset,
  confirmPipelineAsset,
} from "../../api/client";
import type { PipelineAsset } from "../../types";

interface FileUploadProps {
  scriptId: string;
  onUploaded: (asset: PipelineAsset) => void;
}

export function FileUpload({ scriptId, onUploaded }: FileUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadFile = useCallback(
    async (file: File) => {
      setUploading(true);
      setProgress(0);
      setError(null);

      try {
        // 1. Get presigned URL
        const { upload_url, file_key } = await presignPipelineAsset(
          scriptId,
          file.name,
          file.type || undefined,
        );

        // 2. Upload directly to S3 with progress tracking
        await new Promise<void>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open("PUT", upload_url);
          if (file.type) {
            xhr.setRequestHeader("Content-Type", file.type);
          }
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              setProgress(Math.round((e.loaded / e.total) * 100));
            }
          };
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve();
            } else {
              reject(new Error(`Upload failed: ${xhr.status}`));
            }
          };
          xhr.onerror = () => reject(new Error("Upload failed"));
          xhr.send(file);
        });

        // 3. Confirm upload
        const asset = await confirmPipelineAsset(scriptId, {
          file_key,
          file_name: file.name,
          file_size: file.size,
          file_type: file.type || undefined,
        });

        onUploaded(asset);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
        setProgress(0);
      }
    },
    [scriptId, onUploaded],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    },
    [uploadFile],
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) uploadFile(file);
      // Reset input so same file can be re-selected
      e.target.value = "";
    },
    [uploadFile],
  );

  return (
    <div>
      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
          dragOver
            ? "border-violet-500 bg-violet-500/10"
            : "border-white/10 hover:border-white/20 bg-white/[0.02]"
        } ${uploading ? "pointer-events-none opacity-60" : ""}`}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept="video/mp4,video/quicktime,video/*,image/*,.pdf,.doc,.docx"
          onChange={handleFileSelect}
        />
        <div className="text-cream-muted text-sm">
          {uploading ? (
            "Uploading..."
          ) : (
            <>
              <span className="text-cream font-medium">Click to upload</span>{" "}
              or drag and drop
              <br />
              <span className="text-xs text-cream-muted/60 mt-1 block">
                Video (MP4, MOV), images, documents
              </span>
            </>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {uploading && (
        <div className="mt-2">
          <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-violet-500 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-cream-muted mt-1 text-right">{progress}%</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-400 mt-2">{error}</p>
      )}
    </div>
  );
}
