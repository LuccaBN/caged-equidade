# Provisionamento da camada de dados na Aiven (Free Tier)
# Cria um serviço PostgreSQL e o banco "caged" usado pelo ETL.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aiven = {
      source  = "aiven/aiven"
      version = ">= 4.0.0, < 5.0.0"
    }
  }
}

# O token NÃO fica no código: vem da variável aiven_api_token,
# preenchida pelo terraform.tfvars (fora do Git) ou pela variável
# de ambiente TF_VAR_aiven_api_token.
provider "aiven" {
  api_token = var.aiven_api_token
}

resource "aiven_pg" "caged" {
  project      = var.aiven_project
  service_name = var.service_name
  cloud_name   = var.cloud_name
  plan         = var.pg_plan

  pg_user_config {
    pg_version = var.pg_version
  }

  # Evita apagar o banco por acidente em um "terraform destroy"
  termination_protection = var.termination_protection
}

resource "aiven_pg_database" "caged" {
  project       = var.aiven_project
  service_name  = aiven_pg.caged.service_name
  database_name = var.database_name
}
