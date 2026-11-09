import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

export const MANAGE_COURSES_PARAM = "manageCourses";

/** Opens course management once when the page is entered with `?manageCourses=1`, then removes the param. */
export function useManageCoursesDeepLink(onOpen: () => void) {
  const router = useRouter();
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get(MANAGE_COURSES_PARAM) !== "1") return;

    handledRef.current = true;
    onOpen();
    router.replace("/projects");
  }, [onOpen, router]);
}
