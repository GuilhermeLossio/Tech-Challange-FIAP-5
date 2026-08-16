import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 2,
  duration: "15s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

export default function () {
  const base = __ENV.BASE_URL || "http://127.0.0.1:8000";
  for (const path of ["/livez", "/readyz", "/docs", "/openapi.json"]) {
    const response = http.get(`${base}${path}`);
    check(response, { [`${path} is successful`]: (item) => item.status === 200 });
  }
  sleep(1);
}
