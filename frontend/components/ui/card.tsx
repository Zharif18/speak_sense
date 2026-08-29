import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-line bg-white/60 p-6 shadow-[0_1px_0_0_rgba(28,35,33,0.03)]",
        className
      )}
      {...props}
    />
  );
}
