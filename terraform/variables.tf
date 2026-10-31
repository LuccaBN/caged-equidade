variable "aiven_api_token" {
  description = "Token de API da Aiven (User profile > Tokens). Nunca versionar."
  type        = string
  sensitive   = true
}

variable "aiven_project" {
  description = "Nome do projeto já existente na conta Aiven"
  type        = string
}

variable "service_name" {
  description = "Nome do serviço PostgreSQL"
  type        = string
  default     = "pg-caged-equidade"
}

variable "cloud_name" {
  description = "Nuvem/região do serviço. O plano gratuito só existe em algumas regiões; confira no console."
  type        = string
  default     = "do-nyc"
}

variable "pg_plan" {
  description = "Plano do serviço. Gratuito: free-1-1gb (confirme com `avn service plans --service-type pg`)."
  type        = string
  default     = "free-1-1gb"
}

variable "pg_version" {
  description = "Versão do PostgreSQL"
  type        = string
  default     = "16"
}

variable "database_name" {
  description = "Banco usado pelo ETL"
  type        = string
  default     = "caged"
}

variable "termination_protection" {
  description = "Bloqueia a exclusão do serviço pelo Terraform"
  type        = bool
  default     = false
}
