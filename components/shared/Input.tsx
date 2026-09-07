'use client'

import React from 'react'
import { clsx } from 'clsx'
import { motion } from 'framer-motion'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  icon?: React.ReactNode
  hint?: string
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, hint, className = '', ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-[#94A3B8] mb-2">
            {label}
            {props.required && <span className="text-[#e6c3c8] ml-1">*</span>}
          </label>
        )}

        <div className="relative">
          {icon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B]">
              {icon}
            </div>
          )}

          <input
            ref={ref}
            className={clsx(
              'w-full px-4 py-3 rounded-lg text-sm transition-all duration-200',
              'bg-[#0A0A0F] border text-white placeholder-[#475569]',
              'focus:outline-none focus:ring-1',
              error
                ? 'border-[#96203f]/50 focus:border-[#96203f] focus:ring-[#96203f]/20'
                : 'border-[#1E1E2E] hover:border-[#2D2D41] focus:border-[#7C3AED] focus:ring-[#7C3AED]/20',
              icon && 'pl-10',
              className
            )}
            {...props}
          />
        </div>

        {hint && !error && (
          <p className="text-[#64748B] text-xs mt-1.5">{hint}</p>
        )}

        {error && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-[#e6c3c8] text-xs mt-1.5 flex items-center gap-1"
          >
            <span>⚠</span> {error}
          </motion.p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

export default Input