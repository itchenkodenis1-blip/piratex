/** CloudPayments JS Widget type declarations. */

interface CloudPaymentsWidgetOptions {
  publicId: string;
  description: string;
  amount: number;
  currency: string;
  accountId?: string;
  invoiceId?: string;
  email?: string;
  skin?: "mini" | "modern" | "classic";
  data?: Record<string, unknown>;
  requireConfirmation?: boolean;
  configuration?: {
    common?: { successRedirectUrl?: string; failRedirectUrl?: string };
  };
}

interface CloudPaymentsWidget {
  pay(
    scheme: "auth" | "charge",
    options: CloudPaymentsWidgetOptions,
    callbacks?: {
      onSuccess?: (options: Record<string, unknown>) => void;
      onFail?: (reason: string, options: Record<string, unknown>) => void;
      onComplete?: (
        paymentResult: Record<string, unknown>,
        options: Record<string, unknown>,
      ) => void;
    },
  ): void;
}

declare namespace cp {
  class CloudPayments implements CloudPaymentsWidget {
    pay(
      scheme: "auth" | "charge",
      options: CloudPaymentsWidgetOptions,
      callbacks?: {
        onSuccess?: (options: Record<string, unknown>) => void;
        onFail?: (reason: string, options: Record<string, unknown>) => void;
        onComplete?: (
          paymentResult: Record<string, unknown>,
          options: Record<string, unknown>,
        ) => void;
      },
    ): void;
  }
}
