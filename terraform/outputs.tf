output "pg_host" {
  description = "Endereço do PostgreSQL"
  value       = aiven_pg.caged.service_host
}

output "pg_port" {
  description = "Porta do PostgreSQL"
  value       = aiven_pg.caged.service_port
}

output "pg_user" {
  description = "Usuário administrador"
  value       = aiven_pg.caged.service_username
}

output "pg_password" {
  description = "Senha (sensível: exibida só com `terraform output -raw pg_password`)"
  value       = aiven_pg.caged.service_password
  sensitive   = true
}

output "database_url" {
  description = "URL de conexão pronta para o .env do ETL (sensível)"
  value       = "postgresql://${aiven_pg.caged.service_username}:${aiven_pg.caged.service_password}@${aiven_pg.caged.service_host}:${aiven_pg.caged.service_port}/${aiven_pg_database.caged.database_name}?sslmode=require"
  sensitive   = true
}
