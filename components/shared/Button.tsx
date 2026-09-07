'use client'

import React from 'react'
import { clsx } from 'clsx'
import { motion } from 'framer-motion'

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  children: React.ReactNode
  className?: string
  disabled?: boolean
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
  type?: 'button' | 'submit' | 'reset'
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      loading = false,
      children,
      className = '',
      disabled = false,
      onClick,
      type = 'button',
    },
    ref
  ) => {
    const baseStyles =
      'font-semibold rounded-lg transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer relative overflow-hidden'

    const variantStyles = {
      primary:
        'bg-[#7C3AED] hover:bg-[#6D28D9] text-white shadow-lg shadow-purple-900/30 disabled:opacity-50 disabled:cursor-not-allowed',
      secondary:
        'bg-[#13131F] hover:bg-[#1E1E2E] text-white border border-[#2D2D41] hover:border-[#7C3AED] disabled:opacity-50 disabled:cursor-not-allowed',
      outline:
        'border border-[#7C3AED] text-[#A78BFA] hover:bg-[#7C3AED]/10 disabled:opacity-50 disabled:cursor-not-allowed',
      ghost:
        'text-[#94A3B8] hover:text-white hover:bg-[#1E1E2E] disabled:opacity-50 disabled:cursor-not-allowed',
      danger:
        'bg-[#96203f] hover:bg-[#96203f] text-white shadow-lg shadow-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed',
    }

    const sizeStyles = {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-5 py-2.5 text-sm',
      lg: 'px-8 py-3 text-base',
    }

    const isDisabled = disabled || loading

    return (
      <motion.button
        ref={ref}
        type={type}
        onClick={onClick}
        disabled={isDisabled}
        whileHover={!isDisabled ? { scale: 1.02 } : {}}
        whileTap={!isDisabled ? { scale: 0.98 } : {}}
        className={clsx(
          baseStyles,
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
      >
        {loading ? (
          <>
            <div className="w-4 h-4 border-2 border-transparent border-t-current rounded-full animate-spin" />
            <span>Loading...</span>
          </>
        ) : (
          children
        )}
      </motion.button>
    )
  }
)

Button.displayName = 'Button'

export default Button