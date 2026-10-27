import { useEffect, useState } from "react";
export function navigate(path: string) {
  history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
export function usePath() {
  const [state, setState] = useState({
    path: location.pathname,
    search: location.search,
  });
  useEffect(() => {
    const update = () =>
      setState({ path: location.pathname, search: location.search });
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);
  return state.path;
}
