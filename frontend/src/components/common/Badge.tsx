import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "brand" | "success" | "warning" | "danger" | "neutral" | "violet";
  className?: string;
}

const VARIANT_CLASSES: Record<string, string> = {
  brand: "badge-brand",
  success: "badge-success",
  warning: "badge-warning",
  danger: "badge-danger",
  neutral: "badge-neutral",
  violet: "badge-violet",
};

export function Badge({ children, variant = "neutral", className }: BadgeProps) {
  return (
    <span className={cn("badge", VARIANT_CLASSES[variant], className)}>
      {children}
    </span>
  );
}
