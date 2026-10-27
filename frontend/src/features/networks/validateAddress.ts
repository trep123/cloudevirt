function ipv4(value: string): number | null {
  const parts = value.split(".");
  if (
    parts.length !== 4 ||
    parts.some((part) => !/^\d{1,3}$/.test(part) || Number(part) > 255)
  )
    return null;
  return parts.reduce((result, part) => result * 256 + Number(part), 0);
}
function range(cidr: string): [number, number] | null {
  const [address, prefix, ...extra] = cidr.split("/");
  const ip = ipv4(address);
  if (
    extra.length ||
    ip === null ||
    !/^\d{1,2}$/.test(prefix || "") ||
    Number(prefix) > 32
  )
    return null;
  const size = 2 ** (32 - Number(prefix)),
    first = Math.floor(ip / size) * size;
  return [first, first + size - 1];
}
export function validateAddress(
  form: {
    subnet: string;
    gateway: string;
    dhcp_enabled: boolean;
    dhcp_start: string;
    dhcp_end: string;
  },
  existing: string[],
): string | null {
  if (!form.subnet)
    return form.gateway || form.dhcp_enabled
      ? "配置网关或 DHCP 前请填写子网 CIDR"
      : null;
  if (form.subnet.includes(":")) return null; // IPv6 is validated by the server.
  const subnet = range(form.subnet);
  if (!subnet) return "子网 CIDR 格式非法";
  if (
    existing.some((value) => {
      const other = range(value);
      return other && subnet[0] <= other[1] && other[0] <= subnet[1];
    })
  )
    return "该子网与已登记的网络重叠";
  const gateway = form.gateway ? ipv4(form.gateway) : null;
  if (
    form.gateway &&
    (gateway === null || gateway <= subnet[0] || gateway >= subnet[1])
  )
    return "网关须为子网内的可用地址";
  if (form.dhcp_enabled) {
    const start = ipv4(form.dhcp_start),
      end = ipv4(form.dhcp_end);
    if (
      start === null ||
      end === null ||
      start <= subnet[0] ||
      end >= subnet[1] ||
      start > end
    )
      return "DHCP 地址池须位于子网内且起始地址不大于结束地址";
    if (gateway !== null && start <= gateway && gateway <= end)
      return "DHCP 地址池不能包含网关";
  }
  return null;
}
