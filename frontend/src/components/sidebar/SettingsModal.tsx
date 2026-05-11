
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { authFetch } from '@/lib/auth-client';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentFullName: string | null;
}

interface FormData {
  fullName: string;
}

export const SettingsModal = ({ isOpen, onClose, currentFullName }: SettingsModalProps) => {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    defaultValues: {
      fullName: currentFullName || '',
    },
  });

  const onSubmit = async (data: FormData) => {
    setIsLoading(true);
    try {
      const res = await authFetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/auth/me`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: data.fullName }),
      });

      if (!res.ok) {
        const body = await res.json();
        throw new Error(body.detail || 'Failed to update profile');
      }
      
      toast({
        title: "Profile updated",
        description: "Your full name has been updated successfully.",
      });
      
      onClose();
    } catch (error) {
      toast({
        title: "Update failed",
        description: (error as Error)?.message || "Failed to update profile",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Profile Settings</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="fullName" className="text-right">
                Full Name
              </Label>
              <Input
                id="fullName"
                {...register("fullName", { required: "Full name is required" })}
                className="col-span-3"
              />
              {errors.fullName && (
                <p className="col-span-3 col-start-2 text-sm text-destructive">
                  {errors.fullName.message}
                </p>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Saving..." : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
