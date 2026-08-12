"use client";

/**
 * Account settings dialog (Animate UI "tabs for account & password reset"
 * blend) — opened from the user menu in the header. Tab 1 shows the
 * profile, Tab 2 lets the officer rotate their password.
 */
import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { KeyRound, Loader2, ShieldCheck, User } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";

export function AccountDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  const savePassword = async () => {
    if (next.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      toast.error("New password and confirmation do not match.");
      return;
    }
    setSaving(true);
    try {
      await api.changePassword(current, next);
      toast.success("Password updated.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (e) {
      toast.error((e as { message?: string }).message ?? "Failed to update password.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-emerald-500" /> Account Settings
          </DialogTitle>
          <DialogDescription>
            Manage your Tri-Netra Forensics profile and rotate your password.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="account" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="account">
              <User className="mr-1 size-3.5" /> Account
            </TabsTrigger>
            <TabsTrigger value="password">
              <KeyRound className="mr-1 size-3.5" /> Password
            </TabsTrigger>
          </TabsList>

          <TabsContent value="account" className="space-y-4 pt-4">
            <div className="space-y-1.5">
              <Label htmlFor="acc-username">Username</Label>
              <Input id="acc-username" defaultValue={user?.username ?? ""} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="acc-role">Role</Label>
              <Input
                id="acc-role"
                defaultValue={(user?.role ?? "").toUpperCase()}
                disabled
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Username and role are managed by the administrator.
            </p>
          </TabsContent>

          <TabsContent value="password" className="space-y-4 pt-4">
            <div className="space-y-1.5">
              <Label htmlFor="pw-current">Current password</Label>
              <Input
                id="pw-current"
                type="password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw-new">New password</Label>
              <Input
                id="pw-new"
                type="password"
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pw-confirm">Confirm new password</Label>
              <Input
                id="pw-confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
              />
            </div>
            <div className="flex justify-end pt-1">
              <Button onClick={savePassword} disabled={saving}>
                {saving ? <Loader2 className="mr-1 size-4 animate-spin" /> : <KeyRound className="mr-1 size-4" />}
                Save password
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
