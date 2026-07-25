import { useCallback, useEffect, useRef, useState } from "react";
import { getLikedUrls, likeReel, unlikeReel } from "../api/client";

export function useLikes() {
  const [likedUrls, setLikedUrls] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;
    getLikedUrls()
      .then((res) => setLikedUrls(new Set(res.urls)))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const isLiked = useCallback(
    (url: string) => likedUrls.has(url),
    [likedUrls],
  );

  const toggleLike = useCallback(async (url: string) => {
    let wasLiked = false;
    setLikedUrls((prev) => {
      wasLiked = prev.has(url);
      const next = new Set(prev);
      if (wasLiked) next.delete(url);
      else next.add(url);
      return next;
    });
    try {
      if (wasLiked) await unlikeReel(url);
      else await likeReel(url);
    } catch {
      // Revert on error
      setLikedUrls((prev) => {
        const next = new Set(prev);
        if (wasLiked) next.add(url);
        else next.delete(url);
        return next;
      });
    }
  }, []);

  return { likedUrls, isLiked, toggleLike, loading };
}
